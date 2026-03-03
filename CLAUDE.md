# just-apply

Automated job application system. Parent agent searches for jobs, spawns browser subagents to apply.

## Candidate
- **Resume:** `resume/edward_gao_resume.tex`
- **Targets:** Entry-Level / New Grad SWE and ML roles, US (prioritize) and Canada. Prioritize higher-comp companies (top tech, trading firms, well-funded startups) within new grad/entry level.

## Searching for Jobs

### Simplify (Typesense, no auth needed for search)
```python
from simplify_lib.search.client import search_jobs
results = search_jobs(query="software engineer new grad", experience="Entry Level/New Grad", per_page=20)
for hit in results["hits"]:
    doc = hit["document"]
    print(doc["id"], doc["title"], doc["company_name"], doc["locations"])
    # Redirect URL (resolve to get direct career page): https://simplify.jobs/jobs/click/{doc["id"]}
```

### LinkedIn (requires authenticated client via Playwright)
```python
from linkedin_lib.auth import get_client
from linkedin_lib.api import search_jobs, get_job_detail
api = get_client()
jobs = search_jobs(api, "software engineer", count=10, location_name="Canada", company="Databricks")
# Each job: {title, companyName, formattedLocation, listedAt, jobId, url}
detail = get_job_detail(api, jobs[0]["jobId"])
```

**IMPORTANT — Resolving LinkedIn job URLs:** The LinkedIn API does NOT return external apply URLs. Use a **URL resolver subagent** to batch-resolve them:

```
Resolve external apply URLs for these LinkedIn jobs. For each job:
1. Create a tab, navigate to https://www.linkedin.com/jobs/view/{jobId}
2. Wait for load, then click the "Apply" button (blue button with external link icon)
3. A new tab opens with the external career page URL — record the tab ID and URL
4. Close the LinkedIn source tab (no longer needed)

Process all jobs, then run this Python to classify each URL:
```python
import sys; sys.path.insert(0, '/Users/edwarddgao/just-apply')
from pipeline import normalize_url
norm = normalize_url(url)  # strip query params, lowercase, dedupe-ready
```

Return a JSON list (one entry per job):
[{"jobId": "...", "company": "...", "title": "...", "url": "...", "ats": "...", "tab_id": 12345}]

Do NOT fill any forms. Just resolve URLs and classify.
```

The parent agent then filters this list against the tracker and spawns form-filling agents only for automatable, un-applied jobs.

## Checking Tracker (dedup)

**CRITICAL: Always check before applying. Match on URLs, not company/title strings** (tracker truncates titles).
**Re-check tracker before respawning agents** — if agents crashed/disconnected and you're restarting them, refresh tracked URLs first. A previous agent may have submitted before disconnecting.

**Dedup rule:** Only skip if applied within the last 2 weeks. If applied > 2 weeks ago, re-apply.

### Via Chrome JS subagent (preferred — always works when Chrome is open)
**IMPORTANT: Never dump the full tracker URL list** — it's 1400+ URLs and gets truncated in agent responses. Instead, pass candidate URLs TO the tracker subagent and have it return only the match results.

Tracker subagent prompt:
```
Check these candidate URLs against the Simplify tracker. Navigate to simplify.jobs, then run JS to fetch the tracker CSV and check each URL.

Candidate URLs to check:
[LIST OF NORMALIZED URLs]

JS to run on a simplify.jobs tab:
const candidateUrls = [LIST];
const csrf = document.cookie.split('; ').find(c => c.startsWith('csrf='))?.split('=')[1];
const resp = await fetch('https://api.simplify.jobs/v2/candidate/me/tracker/export/csv', {
  credentials: 'include', headers: {'X-CSRF-TOKEN': csrf}
});
const csv = await resp.text();
const lines = csv.trim().split('\n');
const headers = lines[0].split(',');
const urlIdx = headers.indexOf('Job URL');
const dateIdx = headers.indexOf('Applied Date');
const tracked = new Map();
for (let i = 1; i < lines.length; i++) {
  const cols = lines[i].split(',');
  const raw = cols[urlIdx]?.trim();
  if (!raw) continue;
  try {
    const u = new URL(raw);
    const norm = (u.origin + u.pathname).toLowerCase().replace(/\/$/, '');
    const date = cols[dateIdx]?.trim() || '';
    tracked.set(norm, date);
  } catch(e) {}
}
const twoWeeksAgo = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000);
return JSON.stringify(candidateUrls.map(u => {
  const date = tracked.get(u);
  if (!date) return {url: u, status: 'NEW'};
  const d = new Date(date);
  if (d < twoWeeksAgo) return {url: u, status: 'REAPPLY', applied_date: date};
  return {url: u, status: 'SKIP', applied_date: date};
}));

Return the JSON result. Status meanings:
- NEW: never applied, go ahead
- REAPPLY: applied > 2 weeks ago, apply again
- SKIP: applied within last 2 weeks, skip
```

### Via Python (fallback — may 401 if cookies are stale)
```python
from simplify_lib.api.client import SimplifyAPIClient
from simplify_lib.api.tracker import get_tracked_urls

# Client auto-refreshes tokens from Chrome cookies on 401 (requires Chrome cookie flush)
with SimplifyAPIClient() as client:
    tracked_urls = get_tracked_urls(client)  # normalized URL set
```

### Checking a candidate URL
```python
from urllib.parse import urlparse, urlunparse
import httpx

resp = httpx.get(f"https://simplify.jobs/jobs/click/{job_id}", follow_redirects=False)
direct_url = resp.headers["location"]
parsed = urlparse(direct_url)
clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", "")).lower().rstrip("/")
if clean in tracked_urls:
    print("SKIP — already applied")
```

## Pipeline: URL Resolution, Dedup, Validation

Use `pipeline.py` for all pre-processing. All network I/O is async.

```python
import asyncio
from pipeline import filter_jobs, filter_external_urls, validate_urls, normalize_url

# For Simplify search results — resolve redirects (parallel), dedup:
candidates = asyncio.run(filter_jobs(job_ids=["abc123", "def456"], tracked_urls=tracked_urls))
# Returns: [{job_id, direct_url, normalized_url}, ...]

# For LinkedIn jobs (after clicking Apply and getting external URLs):
candidates = filter_external_urls(
    urls=[{"url": "https://jobs.lever.co/...", "company": "X", "tab_id": 123}],
    tracked_urls=tracked_urls,
)

# Pre-validate URLs (HEAD check, catches 404s and error pages):
liveness = asyncio.run(validate_urls([j["direct_url"] for j in candidates]))
candidates = [j for j in candidates if liveness.get(j["direct_url"], False)]
```

IMPORTANT: Never navigate to `simplify.jobs/p/...` and click "Apply" — that opens a new tab outside the MCP tab group. Always resolve the direct URL first, then navigate a group tab to it.

## Marking Jobs as Applied (Tracker)

After an agent confirms submission, mark it in the tracker for dedup.

### Via Chrome JS (preferred)
```javascript
// Run on a simplify.jobs tab
const csrf = document.cookie.split('; ').find(c => c.startsWith('csrf='))?.split('=')[1];
fetch('https://api.simplify.jobs/v2/candidate/me/tracker/applied', {
  method: 'POST',
  credentials: 'include',
  headers: {'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json'},
  body: JSON.stringify({job_posting_id: 'SIMPLIFY_UUID_HERE'})
}).then(r => r.status)
// 200 = success, 409 = already tracked (safe)
```

### Via Python (fallback)
```python
from simplify_lib.api.client import SimplifyAPIClient
from simplify_lib.api.tracker import mark_applied

with SimplifyAPIClient() as client:
    mark_applied(client, job_posting_id)  # Simplify search UUID
# 409 Conflict = already tracked (safe to ignore)
```

For LinkedIn-sourced jobs without a Simplify ID, search Simplify by company name to find the matching job and get its ID.

## Applying to Jobs (Browser Automation)

Parent agent creates a group tab, resolves the direct URL, then navigates to it. Subagents handle the form filling.

### Concurrency & Tab Management
- **Never use visual Chrome MCP tools directly from the parent agent** (screenshots, clicks, form filling, scrolling) — delegate these to subagents. Visual tool results bloat the parent context and cause hallucinations after compaction. Non-visual tools like `tabs_context_mcp` and `tabs_create_mcp` are fine to use directly. Exception: the user may ask you to use visual tools for debugging.
- **Batch processing** — search for jobs, resolve URLs, check tracker, pre-validate URLs, then launch all agents in a single message. Wait for all agents to complete and report before starting the next batch. Do NOT source new jobs or spawn additional agents while a batch is running.
- **Max ~15 agents per batch** — Chrome unloads background tabs beyond this, causing viewport 0x0 errors. If you have more candidates, split into multiple batches.
- **Reuse tabs** — agents cannot close tabs. Instead, pass existing tab IDs to new agents so they navigate reused tabs to new URLs. This prevents tab buildup.
- **Before spawning agents**: resolve all external URLs, check tracker, then **pre-validate with `validate_urls()`** to drop dead links (404s, error pages). Do NOT filter by ATS platform — send agents to everything. Agents try Simplify autofill and report BLOCKED if it doesn't work.
- **Monitor subagent tool_uses** — visible in agent results. Minimize tool uses as much as possible while still successfully submitting. Continuously iterate to drive tool_uses down.
- **After every batch of agents returns, IMMEDIATELY do skill maintenance** — see "After Each Batch: Skill Maintenance" section below. Do not proceed to the next batch until this is done.
- **Essay questions** — agents use a default response for ALL required essay fields: "This is an automated application submitted via Claude Code on behalf of Edward. For any specific questions, please contact him directly at edwarddgao@gmail.com". No custom answers, no escalation, no round-trips.
- **Only add efficiency tactics that come from real subagent feedback** — never invent or guess at optimization tips. If a subagent reports "I wasted 20 clicks scrolling through a dropdown", THEN add "type to filter dropdowns" to the prompt. No data = no rule.
- **Flag contradictions** — if the user says something that contradicts CLAUDE.md, bring it up immediately instead of silently following one or the other.

### Subagent Prompt

Use the `apply-to-job` skill (`.claude/skills/apply-to-job/SKILL.md`). Pass job-specific details via `$ARGUMENTS`:

```
Navigate tab [TAB_ID] to [URL]. Company: [NAME] | Role: [TITLE]
```

The skill contains the complete workflow, known gaps, browser notes, and structured reporting format. **Do not abbreviate or cherry-pick from the skill** — agents receive the full file automatically.

### After Each Batch: Skill Maintenance

Read each agent's **Skill Audit** section and update:
1. Add NEW OBSERVATIONs to the skill's Known Gaps list if actionable
2. Remove gaps that agents consistently report as outdated
3. Update `form-answers.md` with any new Q&A pairs encountered
