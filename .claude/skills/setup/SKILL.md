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

Read `agent_prompt.example.txt` as the template. Use AskUserQuestion to collect the user's information step by step. Do NOT generate answers — every value must come from the user.

#### Step 4a: Resume

Ask the user to provide their resume. Accept either:
- A file path (PDF or tex) — read it and extract the text
- Pasted text

From the resume, extract: name, contact info, education, experience, projects, skills. Show the user what you extracted and confirm it's correct.

#### Step 4b: Known Answers

Ask each question individually via AskUserQuestion. These are the most common questions on job application forms — the agent needs correct answers for all of them.

**Work authorization:**
- "Are you legally authorized to work in [country]?" (Yes/No)
- "Will you now or in the future require sponsorship?" (Yes/No)
- If yes to sponsorship: what visa type?

**Education:**
- GPA (or N/A if they don't want to share)
- Graduation date (month and year)
- Degree type and major

**Employment:**
- Current company (or N/A if unemployed)
- Years of experience (0-1, 1-3, 3-5, 5+)
- Previously worked at any notable companies? (for "have you worked here before" questions)

**Availability:**
- Earliest start date
- Willing to relocate? (Yes/No)
- Willing to work in-person/hybrid? (Yes/No)

**Personal:**
- Pronouns
- GitHub username (if applicable)
- LinkedIn URL (if applicable)
- Personal website/portfolio (if applicable)
- Preferred programming language
- Top 3 programming languages

**Compliance:**
- Security clearance? (Yes/No/Not eligible)
- Non-compete agreement? (Yes/No)
- SMS/text consent for recruiting? (Yes/No)
- BrightHire/background check consent? (Yes/No)

**Preferences:**
- Salary expectations strategy (recommend: "enter 0 or N/A — never give a real number")
- "How did you hear about us?" default answer

#### Step 4c: Essay response

Ask: "What should the agent write for open-ended/essay questions? This gets pasted into every required essay field. Keep it short — 1-2 sentences."

Suggest a generic example but let the user write their own.

#### Step 4d: Generate and confirm

Use all collected answers to generate `agent_prompt.txt` based on the template. Also update:
- The `sqlite3` path in the essay section to match their project directory
- GitHub username references in the Simplify gaps section
- Simplify gap corrections to match their specific answers (e.g., work auth values)

Write the file, then **open it for the user** and ask them to confirm everything is accurate before proceeding. This file controls everything the agent says on their behalf — a wrong answer could misrepresent them to employers.

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

This takes ~30 minutes. Run it in the background and let the user know they can check progress. Full sync also scrapes company ratings automatically (used to rank candidates).

Report when done:
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
