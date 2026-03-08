"""Sync Simplify.jobs Typesense index to local SQLite."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

import httpx

from simplify import TYPESENSE_API_KEY, TYPESENSE_COLLECTION, TYPESENSE_SEARCH

DB_PATH = Path(__file__).parent / "jobs.db"
BATCH_SIZE = 250
MAX_CONCURRENT = 5


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            posting_id TEXT PRIMARY KEY,
            title TEXT,
            company_name TEXT,
            company_id TEXT,
            company_logo TEXT,
            company_size TEXT,
            locations TEXT,
            experience_level TEXT,
            type TEXT,
            functions TEXT,
            min_salary REAL,
            max_salary REAL,
            currency_type TEXT,
            salary_period TEXT,
            sponsors_h1b TEXT,
            updated_date INTEGER,
            start_date INTEGER,
            seasons TEXT,
            majors TEXT,
            travel_requirements TEXT,
            funding_stage TEXT,
            funding_total REAL,
            year_founded INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_updated ON jobs(updated_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_company ON jobs(company_name)")
    conn.commit()


def _row_from_doc(doc: dict) -> tuple:
    return (
        doc.get("posting_id", doc.get("id", "")),
        doc.get("title", ""),
        doc.get("company_name", ""),
        doc.get("company_id", ""),
        doc.get("company_logo", ""),
        doc.get("company_size", ""),
        json.dumps(doc.get("locations", [])),
        json.dumps(doc.get("experience_level", [])),
        doc.get("type", ""),
        json.dumps(doc.get("functions", [])),
        doc.get("min_salary"),
        doc.get("max_salary"),
        doc.get("currency_type", ""),
        str(doc.get("salary_period", "")),
        str(doc.get("sponsors_h1b", "")),
        doc.get("updated_date", 0),
        doc.get("start_date"),
        json.dumps(doc.get("seasons", [])),
        json.dumps(doc.get("majors", [])),
        doc.get("travel_requirements", ""),
        doc.get("funding_stage", ""),
        doc.get("funding_total"),
        doc.get("year_founded"),
    )


UPSERT_SQL = """
    INSERT OR REPLACE INTO jobs (
        posting_id, title, company_name, company_id, company_logo,
        company_size, locations, experience_level, type, functions,
        min_salary, max_salary, currency_type, salary_period, sponsors_h1b,
        updated_date, start_date, seasons, majors, travel_requirements,
        funding_stage, funding_total, year_founded
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


async def _fetch_page(
    client: httpx.AsyncClient, page: int, *, sort_by: str, retries: int = 5
) -> list[dict]:
    payload = json.dumps({
        "searches": [{
            "collection": TYPESENSE_COLLECTION,
            "q": "*",
            "sort_by": sort_by,
            "page": page,
            "per_page": BATCH_SIZE,
        }]
    })
    for attempt in range(retries):
        try:
            resp = await client.post(
                TYPESENSE_SEARCH,
                params={"x-typesense-api-key": TYPESENSE_API_KEY},
                content=payload,
                headers={"Content-Type": "text/plain"},
                timeout=30.0,
            )
            resp.raise_for_status()
            hits = resp.json()["results"][0].get("hits", [])
            return [h["document"] for h in hits]
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError):
            if attempt == retries - 1:
                raise
            await asyncio.sleep(3 ** attempt)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < retries - 1:
                await asyncio.sleep(3 ** attempt)
                continue
            raise


async def full_sync() -> None:
    """Pull entire Typesense index into local SQLite."""
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # Get total count (with retry)
    from simplify import search_jobs
    for _ in range(5):
        try:
            r = search_jobs(query="*", per_page=1)
            break
        except Exception:
            await asyncio.sleep(10)
    else:
        print("Could not reach Typesense after 5 attempts")
        conn.close()
        return
    total = r["found"]
    total_pages = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Full sync: {total} jobs, {total_pages} pages")

    # Check how many we already have (for resume)
    existing = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    if existing > 0:
        start_page = (existing // BATCH_SIZE) + 1
        print(f"  Resuming: {existing} jobs already in DB, starting at page {start_page}")
    else:
        start_page = 1

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    inserted = 0
    t0 = time.time()

    async with httpx.AsyncClient() as client:
        async def fetch_and_store(page: int) -> int:
            async with sem:
                docs = await _fetch_page(
                    client, page, sort_by="posting_id:desc"
                )
            rows = [_row_from_doc(d) for d in docs]
            conn.executemany(UPSERT_SQL, rows)
            return len(rows)

        # Process in chunks to commit periodically
        chunk = 100
        for start in range(start_page, total_pages + 1, chunk):
            end = min(start + chunk, total_pages + 1)
            tasks = [fetch_and_store(p) for p in range(start, end)]
            results = await asyncio.gather(*tasks)
            conn.commit()
            inserted += sum(results)
            total_in_db = existing + inserted
            elapsed = time.time() - t0
            rate = inserted / elapsed if elapsed > 0 else 0
            print(f"  {total_in_db}/{total} ({total_in_db*100//total}%) — {rate:.0f} jobs/s")

    conn.close()
    elapsed = time.time() - t0
    print(f"Done: {inserted} new jobs in {elapsed:.1f}s ({existing + inserted} total)")


async def incremental_sync() -> None:
    """Pull only jobs updated since last sync."""
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    row = conn.execute("SELECT MAX(updated_date) FROM jobs").fetchone()
    last_updated = row[0] if row[0] else 0

    if last_updated == 0:
        conn.close()
        print("No existing data — running full sync instead")
        await full_sync()
        return

    print(f"Incremental sync: fetching jobs updated after {last_updated}")
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    inserted = 0
    page = 1
    done = False

    async with httpx.AsyncClient() as client:
        while not done:
            async with sem:
                docs = await _fetch_page(
                    client, page, sort_by="updated_date:desc"
                )
            if not docs:
                break

            rows = []
            for doc in docs:
                if doc.get("updated_date", 0) <= last_updated:
                    done = True
                    break
                rows.append(_row_from_doc(doc))

            if rows:
                conn.executemany(UPSERT_SQL, rows)
                conn.commit()
                inserted += len(rows)

            page += 1
            if page % 10 == 0:
                print(f"  {inserted} new/updated jobs so far (page {page})")

    conn.close()
    print(f"Incremental sync done: {inserted} new/updated jobs")


def rebuild_candidates() -> None:
    """Rebuild the materialized candidates table used by find_candidates()."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS candidates_new")
    conn.execute("""
        CREATE TABLE candidates_new AS
        SELECT posting_id, title, company_name, locations, max_salary,
               funding_total, company_size, funding_stage, experience_level, functions
        FROM jobs
        WHERE (locations LIKE '%USA%' OR locations LIKE '%Canada%')
          AND type = 'Full-Time'
          AND (experience_level LIKE '%Entry Level/New Grad%'
               OR experience_level LIKE '%Junior%'
               OR LOWER(title) LIKE '%new grad%'
               OR LOWER(title) LIKE '%new college%'
               OR LOWER(title) LIKE '%entry level%'
               OR LOWER(title) LIKE '%university grad%')
          AND (functions LIKE '%Software Engineering%'
               OR functions LIKE '%Backend Engineering%'
               OR functions LIKE '%Frontend Engineering%'
               OR functions LIKE '%Machine Learning%'
               OR functions LIKE '%Data & Analytics%'
               OR functions LIKE '%IT & Security%'
               OR functions LIKE '%DevOps & Infrastructure%'
               OR functions LIKE '%Data Engineering%'
               OR functions LIKE '%Mobile Development%'
               OR functions LIKE '%Emerging Technology%')
          AND (max_salary IS NULL OR max_salary <= 300000)
          AND LOWER(title) NOT LIKE '%senior%'
          AND LOWER(title) NOT LIKE '%staff%'
          AND LOWER(title) NOT LIKE '%principal%'
          AND LOWER(title) NOT LIKE '%lead %'
          AND LOWER(title) NOT LIKE '%director%'
          AND LOWER(title) NOT LIKE '%manager%'
    """)
    conn.execute("CREATE UNIQUE INDEX idx_candidates_new_pid ON candidates_new(posting_id)")
    conn.execute("CREATE INDEX idx_candidates_new_salary ON candidates_new(max_salary)")
    count = conn.execute("SELECT COUNT(*) FROM candidates_new").fetchone()[0]
    conn.execute("DROP TABLE IF EXISTS candidates")
    conn.execute("ALTER TABLE candidates_new RENAME TO candidates")
    conn.commit()
    conn.close()
    print(f"Rebuilt candidates table: {count} rows")


if __name__ == "__main__":
    import sys
    if "--full" in sys.argv:
        asyncio.run(full_sync())
    else:
        asyncio.run(incremental_sync())
    rebuild_candidates()
