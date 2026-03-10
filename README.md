# just-apply

Automated job application system. A Python orchestrator spawns concurrent Claude agents that fill out application forms via Chrome browser automation and Simplify autofill.

## Demo

[![Demo video](https://img.youtube.com/vi/MiDGBzrxSNk/maxresdefault.jpg)](https://youtu.be/MiDGBzrxSNk?si=C9HVTmRYluw_w2gM)

> **Note:** The video shows an earlier version where Claude Code itself orchestrated agents. The pipeline has since moved to a standalone Python script (`pipeline.py`) for better concurrency and cost control. Agents now use Haiku instead of Sonnet (~$0.20 vs ~$3+/run), and only support Lever, Greenhouse, and Ashby — Workday and custom career sites were dropped as they cost ~$5/application and rarely completed successfully.

## How it works

1. **Sync** — Mirror ~864k job postings from Simplify.jobs Typesense index into local SQLite
2. **Filter** — Materialize a `candidates` table (~7.8k rows) using configurable filters in `filters.yaml`
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
       concurrent workers, each with a fixed Chrome tab
```

## Supported ATS platforms

- Lever (`lever.co`)
- Greenhouse (`greenhouse.io`)
- Ashby (`ashbyhq.com`)

## Getting started

Requires [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Google Chrome, and the [Simplify](https://simplify.jobs) browser extension.

```bash
pip install httpx pyyaml
```

Then run the interactive setup wizard inside Claude Code:

```
/setup
```

This will verify prerequisites, generate your `agent_prompt.txt` (resume + known answers), customize `filters.yaml`, and run the first database sync.

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
python sync.py --full               # full sync (~30 min)
python sync.py --rebuild            # reapply filters without syncing
python search.py                    # preview candidates
python search.py --manual           # preview manual-apply queue
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
