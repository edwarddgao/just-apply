# just-apply

Automated job application system. A Python orchestrator spawns concurrent Claude agents that fill out application forms via Chrome browser automation and Simplify autofill.

## Demo

[![Demo video](https://img.youtube.com/vi/MiDGBzrxSNk/maxresdefault.jpg)](https://youtu.be/MiDGBzrxSNk?si=C9HVTmRYluw_w2gM)

> **Note:** Video shows an earlier version. Pipeline now uses a standalone script with Haiku agents on Lever/Greenhouse/Ashby only.

## Getting started

1. Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
2. Open this project in Claude Code and run:

```
/setup
```

The wizard verifies prerequisites, installs dependencies, generates your `agent_prompt.txt`, customizes `filters.yaml`, and runs the first database sync.

**Important:** Review `agent_prompt.txt` before running the pipeline. It contains everything the agent will say on your behalf — personal info, work authorization answers, and essay responses.

## Usage

Everything runs through Claude Code. Just tell it what you want:

- **"start applying"** — runs the pipeline to auto-apply to jobs
- **"sync the database"** — pulls latest postings from Simplify
- **"show candidates"** — previews top-rated jobs
- **"/apply-manual 10"** — opens platform-blocked jobs in Chrome for manual application

### CLI reference

Under the hood, Claude Code runs these commands:

```bash
python pipeline.py                  # auto-apply (default: 1 concurrent agent)
python pipeline.py --concurrency 4  # multiple agents
python sync.py                      # incremental sync (~1 min)
python sync.py --full               # full sync + company ratings (~30 min)
python sync.py --rebuild            # reapply filters without syncing
python scrape_companies.py          # scrape company ratings only
python search.py                    # preview candidates
python search.py --manual           # preview manual-apply queue
```

## How it works

1. **Sync** — Mirror ~864k job postings from Simplify.jobs Typesense index into local SQLite
2. **Filter** — Materialize a `candidates` table using configurable filters in `filters.yaml`
3. **Resolve** — Follow simplify.jobs redirects to external career pages, filter to supported ATS platforms (Lever, Greenhouse, Ashby)
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
       concurrent workers, each with a fixed Chrome tab
```

## Cost

Pipeline agents use Haiku. Effective cost is about **$0.50 per successful submission**.

Estimated submissions per Claude Code plan:

| Plan | Price | API equiv* | Est. submissions/month |
|------|-------|-----------|----------------------|
| Pro | $20/mo | ~$150 | ~300 |
| Max 5x | $100/mo | ~$1,350 | ~2,700 |
| Max 20x | $200/mo | ~$5,000 | ~10,000 |

*API credit equivalents are community estimates, not official Anthropic numbers.*
