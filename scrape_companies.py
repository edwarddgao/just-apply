"""Scrape company data (ratings, funding, size) from Simplify.jobs company pages."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import time
from pathlib import Path

import httpx

DB_PATH = Path(__file__).parent / "jobs.db"
MAX_CONCURRENT = 10
BATCH_SIZE = 100

NEXT_DATA_RE = re.compile(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    company_id TEXT PRIMARY KEY,
    name TEXT,
    rating_competitive_edge INTEGER,
    rating_growth_potential INTEGER,
    rating_differentiation INTEGER,
    funding_total REAL,
    funding_stage TEXT,
    company_size INTEGER,
    year_founded INTEGER,
    industries TEXT,
    scraped_at INTEGER
)
"""

UPSERT_SQL = """
INSERT OR REPLACE INTO companies (
    company_id, name, rating_competitive_edge, rating_growth_potential,
    rating_differentiation, funding_total, funding_stage, company_size,
    year_founded, industries, scraped_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _row_from_company(c: dict, scraped_at: int) -> tuple:
    industries = c.get("industries") or []
    return (
        c.get("id", ""),
        c.get("name", ""),
        c.get("rating_competitive_edge"),
        c.get("rating_growth_potential"),
        c.get("rating_differentiation"),
        c.get("funding_total"),
        c.get("funding_stage", ""),
        c.get("company_size"),
        c.get("year_founded"),
        json.dumps([i.get("name", "") for i in industries]) if industries else "[]",
        scraped_at,
    )


async def fetch_company(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, company_id: str
) -> tuple | None:
    url = f"https://simplify.jobs/c/{company_id}"
    async with sem:
        for attempt in range(3):
            try:
                resp = await client.get(url, timeout=15.0, follow_redirects=True)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                m = NEXT_DATA_RE.search(resp.text)
                if not m:
                    return None
                data = json.loads(m.group(1))
                company = data.get("props", {}).get("pageProps", {}).get("company")
                if not company:
                    return None
                return _row_from_company(company, int(time.time()))
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ConnectError):
                if attempt == 2:
                    return None
                await asyncio.sleep(2 ** attempt)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                if e.response.status_code >= 500 and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
    return None


async def scrape_all() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA_SQL)
    conn.commit()

    # Get all company IDs from jobs table
    all_ids = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT company_id FROM jobs WHERE company_id <> ''"
        ).fetchall()
    ]

    # Skip already scraped
    existing = {
        r[0] for r in conn.execute("SELECT company_id FROM companies").fetchall()
    }
    remaining = [cid for cid in all_ids if cid not in existing]

    print(f"Companies: {len(all_ids)} total, {len(existing)} already scraped, {len(remaining)} remaining")
    if not remaining:
        print("Nothing to scrape.")
        conn.close()
        return

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    scraped = 0
    failed = 0
    t0 = time.time()

    async with httpx.AsyncClient() as client:
        for i in range(0, len(remaining), BATCH_SIZE):
            chunk = remaining[i : i + BATCH_SIZE]
            results = await asyncio.gather(
                *[fetch_company(client, sem, cid) for cid in chunk]
            )

            rows = [r for r in results if r is not None]
            failed += len(chunk) - len(rows)
            if rows:
                conn.executemany(UPSERT_SQL, rows)
                conn.commit()
                scraped += len(rows)

            elapsed = time.time() - t0
            rate = scraped / elapsed if elapsed > 0 else 0
            total_done = len(existing) + scraped
            print(
                f"  {total_done}/{len(all_ids)} ({total_done * 100 // len(all_ids)}%) "
                f"— {rate:.1f}/s, {failed} failed"
            )

    conn.close()
    elapsed = time.time() - t0
    print(f"\nDone: {scraped} scraped, {failed} failed in {elapsed:.0f}s")


if __name__ == "__main__":
    asyncio.run(scrape_all())
