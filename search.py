"""Query local job database for application candidates."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import httpx

DB_PATH = Path(__file__).parent / "jobs.db"

def find_candidates(limit: int = 100) -> list[dict]:
    """Return unapplied jobs ranked by capped salary DESC.

    Uses the materialized `candidates` table (rebuilt by sync.py) for speed.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT c.*
        FROM candidates c
        LEFT JOIN applications a ON c.posting_id = a.posting_id
        LEFT JOIN blocked b ON c.posting_id = b.posting_id
        WHERE a.posting_id IS NULL
          AND b.posting_id IS NULL
        ORDER BY COALESCE(c.max_salary, 0) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    conn.close()

    return [
        {
            "posting_id": r["posting_id"],
            "title": r["title"],
            "company": r["company_name"],
            "locations": json.loads(r["locations"]),
            "max_salary": r["max_salary"],
            "funding_total": r["funding_total"],
            "company_size": r["company_size"],
        }
        for r in rows
    ]


async def resolve_urls(candidates: list[dict], concurrency: int = 5) -> list[dict]:
    """Resolve posting_id → external career page URL via simplify.jobs redirect.

    Adds 'url' key to each candidate dict. Drops candidates that fail to resolve.
    """
    sem = asyncio.Semaphore(concurrency)

    async def resolve_one(client: httpx.AsyncClient, c: dict) -> dict | None:
        url = f"https://simplify.jobs/jobs/click/{c['posting_id']}"
        async with sem:
            for attempt in range(3):
                try:
                    resp = await client.get(url, follow_redirects=True, timeout=15.0)
                    final = str(resp.url)
                    if "simplify.jobs" in final:
                        return None
                    # Detect dead pages before spawning an agent
                    if resp.status_code == 404:
                        return {**c, "url": final, "_dead": "HTTP 404"}
                    if "workdayjobs.com" in final and "postingAvailable: false" in resp.text:
                        return {**c, "url": final, "_dead": "Workday posting unavailable"}
                    return {**c, "url": final}
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ConnectError):
                    if attempt == 2:
                        return None
                    await asyncio.sleep(2**attempt)
                except httpx.HTTPStatusError:
                    return None
        return None

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[resolve_one(client, c) for c in candidates])

    return [r for r in results if r is not None]


def mark_applied(posting_id: str) -> None:
    """Record a successful application."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO applications (posting_id, applied_at) VALUES (?, datetime('now'))",
        (posting_id,),
    )
    conn.commit()
    conn.close()


def mark_blocked(posting_id: str, reason: str, company: str = "", title: str = "", url: str = "") -> None:
    """Record a job that can't be automated. Excluded from future batches."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO blocked (posting_id, reason, company, title, url, blocked_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (posting_id, reason, company, title, url),
    )
    conn.commit()
    conn.close()


def list_blocked() -> list[dict]:
    """Return all blocked jobs for manual application."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM blocked ORDER BY blocked_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    candidates = find_candidates(limit=20)
    print(f"Candidates: {len(candidates)}")
    print()
    for i, c in enumerate(candidates, 1):
        sal = f"${int(c['max_salary']/1000)}k" if c["max_salary"] else ""
        locs = ", ".join(c["locations"][:2])
        print(f"{i:>3}. {c['company']:<28} {c['title'][:45]:<45} {sal:>6}  {locs}")
