# just-apply

Automated job application system. Python orchestrator spawns `claude -p` agents to fill forms via Chrome MCP.

## Architecture

```
pipeline.py (Python)          claude -p --chrome (per job)
┌─────────────────────┐       ┌─────────────────────┐
│ find_candidates()   │       │ agent_prompt.txt     │
│ resolve_urls()      │──────>│ Simplify autofill    │
│ mark_applied()      │<──────│ Chrome MCP tools     │
│ mark_excluded()     │       │ stream-json log      │
└─────────────────────┘       └─────────────────────┘
        concurrent workers, each with a fixed tab ID
```

## Running

```bash
python pipeline.py                  # 1 concurrent (default), runs until DB exhausted
python pipeline.py --concurrency 4
```

If run from inside Claude Code, prefix with `env -u CLAUDECODE` to bypass nesting check.

## Files

- `pipeline.py` — orchestrator: fetches jobs, resolves URLs, spawns agents, marks results
- `search.py` — `find_candidates()` (queries `candidates` table), `mark_applied()`, `mark_excluded()`, `delete_job()`
- `sync.py` — syncs Simplify.jobs Typesense → `jobs.db`, rebuilds `candidates` table
- `simplify.py` — Typesense API client (used by sync only)
- `jobs.db` — SQLite mirror (864k+ jobs), `candidates` table (pre-filtered ~7.8k rows)
- `logs/` — per-job stream-json logs for debugging (`logs/{posting_id}.jsonl`)
- `agent_prompt.txt` — system prompt for pipeline agents (resume, workflow, known gaps)

## Candidate

- **Resume:** `resume/edward_gao_resume.tex`
- **Targets:** Entry-Level / New Grad SWE and ML roles, US (prioritize) and Canada

## Database

### `candidates` table (materialized view)
Pre-filtered from `jobs` table by location, experience, function, title, company. Rebuilt by `sync.py` after each sync. Query is ~6ms vs ~700ms on raw `jobs` table.

### Filters applied by `find_candidates()`:
- Location: USA or Canada
- Type: Full-Time
- Experience: Entry Level/New Grad or Junior
- Functions: SWE, Backend, Frontend, ML, Data, DevOps, etc.
- Salary: ≤ $300k
- Title exclusion: no senior, staff, principal, lead, director, manager, phd
- Company exclusion: no SpaceX (US citizenship required)
- Dedup: excludes posting_ids in `applications` or `exclusions` tables

### Syncing
- Full: `python sync.py --full` (~30 min)
- Incremental: `python sync.py` (fetches jobs updated since last sync)
- Both rebuild the `candidates` table at the end

## Tracking

- **SUBMITTED / ALREADY_APPLIED** → `mark_applied(posting_id)`
- **BLOCKED / TIMEOUT** → `mark_excluded(posting_id, reason, ...)` — goes to manual apply queue
- **Dead posting (404)** → `delete_job(posting_id)` — removed from all tables
- **ERROR** → stays in pool for retry (not recorded)

### `exclusions` table
Two block types:
- `platform` — can't automate (wrong ATS, timeout, complex portal). Surfaces in manual apply queue.
- `skipped` — user passed during manual apply. Never shown again.

## Pipeline Details

### How it works
1. `find_candidates(limit=10)` → get candidates from DB
2. `resolve_urls()` → follow simplify.jobs redirects to external career pages (batched)
3. Pre-filter to allowed ATS domains (lever.co, greenhouse.io, ashbyhq.com)
4. Worker grabs free tab → spawns `claude -p --chrome --model haiku` with agent_prompt.txt
5. Agent fills form, reports STATUS
6. Parse stream-json log → mark result → worker takes next job

### Error handling
- 3+ errors within 60 seconds → stop (Chrome likely crashed)
- Per-job timeout: 600s
- Worker exceptions caught
- DB is the only state — just restart the script to resume
- Unresolvable URLs excluded immediately (manual apply queue)

### Allowed ATS platforms
Defined in `pipeline.py` as `ALLOWED_DOMAINS`: lever.co, greenhouse.io, ashbyhq.com

### Agent prompt
```
Navigate tab {TAB_ID} to {URL}. Company: {NAME} | Role: {TITLE}
```

## Skill Maintenance

After reviewing agent logs in `logs/`, update `agent_prompt.txt`:
1. Add cross-platform observations to Known Gaps
2. Remove outdated gaps
3. Update Known Answers with new Q&A pairs
4. Do NOT add company-specific form quirks
