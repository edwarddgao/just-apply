"""Sync Simplify.jobs Typesense index to local SQLite."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

import httpx

from simplify import TYPESENSE_API_KEY, TYPESENSE_COLLECTION, TYPESENSE_SEARCH
from search import TITLE_EXCLUSIONS, COMPANY_EXCLUSIONS

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            posting_id TEXT PRIMARY KEY,
            applied_at TEXT
        )
    """)
    # Migration: rename blocked → exclusions
    has_blocked = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blocked'").fetchone()
    if has_blocked:
        # Drop empty exclusions table if it exists (from a partial migration)
        conn.execute("DROP TABLE IF EXISTS exclusions")
        conn.execute("ALTER TABLE blocked RENAME TO exclusions")
        # Rename blocked_at → excluded_at
        # SQLite ALTER TABLE RENAME COLUMN requires 3.25+
        cols = {r[1] for r in conn.execute("PRAGMA table_info(exclusions)").fetchall()}
        if "blocked_at" in cols:
            conn.execute("ALTER TABLE exclusions RENAME COLUMN blocked_at TO excluded_at")
        # Add block_type if missing (very old schema)
        if "block_type" not in cols:
            conn.execute("ALTER TABLE exclusions ADD COLUMN block_type TEXT DEFAULT 'platform'")
        # Reclassify: all permanent → platform (no permanent type anymore)
        conn.execute("UPDATE exclusions SET block_type = 'platform' WHERE block_type = 'permanent'")
        # Delete dead entries (404s, unavailable) — these should be removed from jobs too
        dead_reasons = conn.execute("""
            SELECT posting_id FROM exclusions
            WHERE reason LIKE 'Workday 404%'
               OR reason LIKE 'Workday posting unavailable%'
               OR reason LIKE 'URL resolution failed%'
               OR reason LIKE 'HTTP 404%'
        """).fetchall()
        if dead_reasons:
            dead_tuples = [(r[0],) for r in dead_reasons]
            conn.executemany("DELETE FROM jobs WHERE posting_id = ?", dead_tuples)
            conn.executemany("DELETE FROM exclusions WHERE posting_id = ?", dead_tuples)
    # Create exclusions table if fresh DB (no blocked to migrate)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exclusions (
            posting_id TEXT PRIMARY KEY,
            reason TEXT,
            company TEXT,
            title TEXT,
            url TEXT,
            excluded_at TEXT,
            block_type TEXT DEFAULT 'platform'
        )
    """)
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
            if e.response.status_code >= 500:
                if attempt == retries - 1:
                    raise
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
    seen_ids: set[str] = set()
    inserted = 0
    t0 = time.time()

    async with httpx.AsyncClient() as client:
        async def fetch_and_store(page: int) -> tuple[int, list[str]]:
            async with sem:
                docs = await _fetch_page(
                    client, page, sort_by="posting_id:desc"
                )
            rows = [_row_from_doc(d) for d in docs]
            ids = [d.get("posting_id", d.get("id", "")) for d in docs]
            conn.executemany(UPSERT_SQL, rows)
            return len(rows), ids

        # Process in chunks to commit periodically
        chunk = 100
        for start in range(start_page, total_pages + 1, chunk):
            end = min(start + chunk, total_pages + 1)
            tasks = [fetch_and_store(p) for p in range(start, end)]
            results = await asyncio.gather(*tasks)
            conn.commit()
            for count, ids in results:
                inserted += count
                seen_ids.update(ids)
            total_in_db = existing + inserted
            elapsed = time.time() - t0
            rate = inserted / elapsed if elapsed > 0 else 0
            print(f"  {total_in_db}/{total} ({total_in_db*100//total}%) — {rate:.0f} jobs/s")

    # Delete jobs not seen in Typesense (dead postings)
    # Only purge if we did a complete sync (not a resume)
    dead_count = 0
    if start_page == 1:
        all_db_ids = {r[0] for r in conn.execute("SELECT posting_id FROM jobs").fetchall()}
        dead_ids = all_db_ids - seen_ids
        if dead_ids:
            dead_tuples = [(pid,) for pid in dead_ids]
            conn.executemany("DELETE FROM jobs WHERE posting_id = ?", dead_tuples)
            conn.executemany("DELETE FROM exclusions WHERE posting_id = ?", dead_tuples)
            conn.commit()
            dead_count = len(dead_ids)
            print(f"Purged {dead_count} dead postings")
    else:
        print("Skipping dead-posting purge (resumed sync, seen_ids incomplete)")

    conn.close()
    elapsed = time.time() - t0
    print(f"Done: {inserted} new jobs in {elapsed:.1f}s, {dead_count} purged")


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
    title_filter = " ".join(f"AND LOWER(j.title) NOT LIKE '%{t}%'" for t in TITLE_EXCLUSIONS)
    company_filter = " ".join(f"AND LOWER(j.company_name) NOT LIKE '%{c}%'" for c in COMPANY_EXCLUSIONS)
    conn.execute("DROP TABLE IF EXISTS candidates_new")
    conn.execute(f"""
        CREATE TABLE candidates_new AS
        SELECT j.posting_id, j.title, j.company_name, j.locations, j.max_salary,
               COALESCE(co.funding_total, j.funding_total) as funding_total,
               j.company_size, j.funding_stage, j.experience_level, j.functions,
               COALESCE(co.rating_competitive_edge, 0) as rating_competitive_edge,
               COALESCE(co.rating_growth_potential, 0) as rating_growth_potential,
               COALESCE(co.rating_differentiation, 0) as rating_differentiation
        FROM jobs j
        LEFT JOIN companies co ON j.company_id = co.company_id
        WHERE (j.locations LIKE '%USA%' OR j.locations LIKE '%Canada%')
          AND j.type = 'Full-Time'
          AND (j.experience_level LIKE '%Entry Level/New Grad%'
               OR j.experience_level LIKE '%Junior%'
               OR LOWER(j.title) LIKE '%new grad%'
               OR LOWER(j.title) LIKE '%new college%'
               OR LOWER(j.title) LIKE '%entry level%'
               OR LOWER(j.title) LIKE '%university grad%')
          AND (j.functions LIKE '%Software Engineering%'
               OR j.functions LIKE '%Backend Engineering%'
               OR j.functions LIKE '%Frontend Engineering%'
               OR j.functions LIKE '%Machine Learning%'
               OR j.functions LIKE '%Data & Analytics%'
               OR j.functions LIKE '%IT & Security%'
               OR j.functions LIKE '%DevOps & Infrastructure%'
               OR j.functions LIKE '%Data Engineering%'
               OR j.functions LIKE '%Mobile Development%'
               OR j.functions LIKE '%Emerging Technology%')
          AND (j.max_salary IS NULL OR j.max_salary <= 300000)
          AND j.salary_period <> '1'
          {title_filter}
          {company_filter}
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_new_pid ON candidates_new(posting_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_new_salary ON candidates_new(max_salary)")
    count = conn.execute("SELECT COUNT(*) FROM candidates_new").fetchone()[0]
    conn.execute("DROP TABLE IF EXISTS candidates")
    conn.execute("ALTER TABLE candidates_new RENAME TO candidates")
    conn.commit()
    conn.close()
    print(f"Rebuilt candidates table: {count} rows")


async def check_liveness() -> None:
    """Remove jobs/candidates/exclusions entries whose postings are no longer in Typesense."""
    conn = sqlite3.connect(DB_PATH)

    all_ids = [r[0] for r in conn.execute("SELECT posting_id FROM candidates").fetchall()]

    if not all_ids:
        print("Liveness check: no posting_ids to check")
        conn.close()
        return

    print(f"Liveness check: {len(all_ids)} posting_ids to verify")
    live_ids: set[str] = set()
    failed_ids: set[str] = set()

    async with httpx.AsyncClient() as client:
        for i in range(0, len(all_ids), BATCH_SIZE):
            batch = all_ids[i : i + BATCH_SIZE]
            filter_val = ",".join(f"`{pid}`" for pid in batch)
            payload = json.dumps({
                "searches": [{
                    "collection": TYPESENSE_COLLECTION,
                    "q": "*",
                    "filter_by": f"posting_id:=[{filter_val}]",
                    "per_page": BATCH_SIZE,
                    "include_fields": "posting_id",
                }]
            })
            for attempt in range(3):
                try:
                    resp = await client.post(
                        TYPESENSE_SEARCH,
                        params={"x-typesense-api-key": TYPESENSE_API_KEY},
                        content=payload,
                        headers={"Content-Type": "text/plain"},
                        timeout=30.0,
                    )
                    resp.raise_for_status()
                    for hit in resp.json()["results"][0].get("hits", []):
                        live_ids.add(hit["document"]["posting_id"])
                    break
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError):
                    if attempt == 2:
                        print(f"  Warning: batch {i // BATCH_SIZE} failed after retries")
                        failed_ids.update(batch)
                    await asyncio.sleep(2 ** attempt)

    # Exclude failed batches from dead calculation — don't delete what we couldn't verify
    dead_ids = set(all_ids) - live_ids - failed_ids
    if dead_ids:
        dead_tuples = [(pid,) for pid in dead_ids]
        conn.executemany("DELETE FROM jobs WHERE posting_id = ?", dead_tuples)
        conn.executemany("DELETE FROM candidates WHERE posting_id = ?", dead_tuples)
        conn.commit()

    conn.close()
    print(f"Liveness check: {len(live_ids)} alive, {len(dead_ids)} dead (removed)")


if __name__ == "__main__":
    import sys
    if "--full" in sys.argv:
        asyncio.run(full_sync())
    else:
        asyncio.run(incremental_sync())
        asyncio.run(check_liveness())
    rebuild_candidates()
