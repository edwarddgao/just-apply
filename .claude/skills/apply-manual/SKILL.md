---
name: apply-manual
description: Open top-rated manual-apply jobs in Chrome tabs. User applies manually, then Claude marks results.
user-invocable: true
arguments: "count - number of jobs to open, default 10"
---

# Manual Apply Workflow

Opens the top-rated platform-blocked jobs in Chrome tabs for the user to apply to manually.

## Steps

### 1. Fetch candidates

```python
from search import find_manual_candidates, mark_applied, mark_excluded
jobs = find_manual_candidates(limit=COUNT)  # COUNT from argument, default 10
```

### 2. Open tabs

- Call `tabs_context_mcp` with `createIfEmpty=true`
- For each job, call `tabs_create_mcp` then `navigate` to the job URL
- Track mapping: `{tab_id: job}` for each opened tab
- Print the list of opened jobs with their scores

### 3. Wait for user

Tell the user:
- Apply to jobs you want in the browser
- Close tabs you want to skip
- Say "done" when finished

### 4. Check results

When the user says "done":
- Call `tabs_context_mcp` to get remaining open tabs
- For each original tab:
  - If still open → `mark_applied(posting_id)` and log as applied
  - If closed → `mark_excluded(posting_id, "Skipped (manual)", company, title, url, block_type="skipped")` so it doesn't reappear
- Print summary: X applied, Y skipped
