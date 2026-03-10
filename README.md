# just-apply

Automated job application system. A Python orchestrator spawns concurrent Claude agents that fill out application forms via Chrome browser automation and Simplify autofill.

## Demo

https://youtu.be/MiDGBzrxSNk?si=C9HVTmRYluw_w2gM

## How it works

1. **Sync** — Mirror ~864k job postings from Simplify.jobs Typesense index into local SQLite
2. **Filter** — Materialize a `candidates` table (~7.8k rows) by location, experience level, function, title, and company
3. **Resolve** — Follow simplify.jobs redirects to external career pages, filter to supported ATS platforms
4. **Apply** — Spawn `claude -p --chrome` agents that navigate to each posting, trigger Simplify autofill, fix validation errors, and submit
5. **Track** — Record results in SQLite: applied, excluded (manual queue), or deleted (dead posting)

```
pipeline.py (Python)          claude -p --chrome (per job)
+-----------------------+     +-----------------------+
| find_candidates()     |     | agent_prompt.txt      |
| resolve_urls()        |---->| Simplify autofill     |
| mark_applied()        |<----| Chrome MCP tools      |
| mark_excluded()       |     | stream-json log       |
+-----------------------+     +-----------------------+
       x4 concurrent workers, each with a fixed Chrome tab
```

## Supported ATS platforms

- Lever (`lever.co`)
- Greenhouse (`greenhouse.io`)
- Ashby (`ashbyhq.com`)

## Setup

Requires:
- Python 3.11+
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) with Chrome MCP
- [Simplify](https://simplify.jobs) browser extension (for autofill)
- Google Chrome

```bash
pip install httpx
```

## Usage

```bash
# First run: full sync to populate the database (~30 min)
python sync.py --full

# Subsequent runs: incremental sync (~1 min)
python sync.py

# Run pipeline (1 concurrent agent by default)
python pipeline.py
python pipeline.py --concurrency 4  # multiple agents

# Preview candidates ranked by company rating (doesn't apply)
python search.py

# Preview platform-blocked jobs for manual application
python search.py --manual
```

## Cost

~$0.15-0.22 per application (Lever/Ashby, using Haiku).
