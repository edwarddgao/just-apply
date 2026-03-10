---
name: setup
description: Interactive setup wizard — verifies prerequisites, generates agent_prompt.txt and filters.yaml, runs first sync.
user-invocable: true
arguments: ""
---

# Setup Wizard

Guides the user through first-time setup of just-apply.

## Steps

### 1. Verify prerequisites

Check each and report status. If any fail, explain how to fix before continuing.

```bash
# Python 3.11+
python3 --version

# Required packages
python3 -c "import httpx; import yaml; print('ok')"

# Claude CLI
claude --version

# Google Chrome installed
ls "/Applications/Google Chrome.app" 2>/dev/null || ls "/usr/bin/google-chrome" 2>/dev/null
```

If packages are missing, offer to run `pip install httpx pyyaml`.

### 2. Verify Chrome MCP

Check if Claude CLI has Chrome MCP configured:

```bash
claude mcp list 2>/dev/null
```

If Chrome MCP is not listed, tell the user:
- Install the [Claude in Chrome](https://chromewebstore.google.com/detail/claude-in-chrome/odciglefcoihjkbienpomfadjckmcamgp) extension
- Then run: `claude mcp add --transport chrome chrome`
- Link: https://docs.anthropic.com/en/docs/claude-code/chrome-mcp

### 3. Verify Simplify extension

Open Chrome and check if Simplify is installed:

- Call `tabs_context_mcp` with `createIfEmpty=true`
- Call `navigate` to `https://simplify.jobs`
- Take a screenshot — look for the Simplify "S" icon in the toolbar

If not visible, tell the user:
- Install from https://simplify.jobs
- Create a Simplify account and fill out their profile (name, education, experience)
- Upload their resume PDF to Simplify
- This is critical — Simplify handles autofill and resume uploads

### 4. Generate agent_prompt.txt

Read `agent_prompt.example.txt` as the template. Ask the user for their information to fill it in.

**Ask the user to provide their resume.** Accept either:
- A file path (PDF or tex) — read it and extract the text
- Pasted text

Then ask for the remaining Known Answers that aren't covered by the resume:
- Work authorization status (for each country they're targeting)
- Visa/sponsorship status
- GPA
- Graduation date
- Current company (or N/A)
- Security clearance eligibility
- Pronouns
- GitHub username
- Preferred programming language(s)
- Years of experience level
- Any other details they want to include

Also ask the user what they want as their **default essay/open-ended response** — this gets pasted into every required essay field. Suggest they keep it short and generic.

Use all of this to generate `agent_prompt.txt` based on the template. Also update:
- The essay response with what the user provided
- The `sqlite3` path in the essay section to match their project directory
- GitHub username references
- Any Simplify gap corrections specific to their answers

Write the file and show the user a summary of what was generated.

**IMPORTANT:** Tell the user to carefully review `agent_prompt.txt` before running the pipeline. This file controls everything the agent will say on their behalf — personal info, work authorization answers, and essay responses. A wrong answer could misrepresent them to employers. Open the file for them and ask them to confirm it's accurate.

### 5. Customize filters.yaml

If `filters.yaml` doesn't exist, copy `filters.example.yaml` to `filters.yaml` first. Then ask the user:

- What **locations** are you targeting? (show available: USA, Canada, or others)
- What **experience levels**? (show available: Entry Level/New Grad, Junior, Mid Level, Senior, Expert or higher, Internship)
- What **job functions**? (show the current list and ask if they want to add/remove any)
- **Max salary** filter? (current default: $300k)
- Any **title keywords to exclude**? (show current list)
- Any **companies to exclude**? (show current list, explain why — e.g., citizenship requirements)

Write the updated `filters.yaml`.

### 6. Initial sync and rebuild

Ask the user if they want to run the first sync now. If yes:

```bash
python3 sync.py --full
```

This takes ~30 minutes. Run it in the background and let the user know they can check progress.

After sync completes, report:
- Total jobs synced
- Candidates matching their filters
- Ready to run `python pipeline.py`

### 7. Summary

Print a summary:
- Prerequisites: all verified
- `agent_prompt.txt`: generated with their info
- `filters.yaml`: customized
- Database: synced (if they chose to sync)
- Next step: `python pipeline.py` to start applying
