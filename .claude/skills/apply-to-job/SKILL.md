---
name: apply-to-job
description: Fill out a job application form using Simplify autofill. Supports both direct ATS URLs and LinkedIn job URLs (auto-resolves to external career page).
---

# Job Application Form Filler

Your assignment (tab ID, URL, company, role) is provided in the agent prompt that loaded this skill.

## Setup

Read this file before starting:
- /Users/edwarddgao/just-apply/resume/edward_gao_resume.tex (candidate resume)

## Known Answers

- **Sponsorship (US):** Yes — needs visa sponsorship. Work auth (US): No. Visa type: TN (Canadian citizen).
- **Sponsorship (Canada):** No — Canadian citizen.
- **GPA:** 3.8
- **Earliest start date:** As soon as possible / Immediately
- **Graduation date:** April 2025
- **Willing to relocate / work in-person:** Yes
- **Previously worked at [company]:** No (except Amazon — Yes)
- **Current Company:** Amazon
- **How did you hear:** Job Board / Simplify
- **Salary expectations:** Never provide a real number. Use "N/A", "$0", or 0.
- **SMS/text consent:** No
- **Security clearance:** No / not eligible (Canadian citizen)
- **Pronouns:** He/Him
- **Personal project:** https://artalike.org
- **Preferred programming language:** Python. Top 3: Python, TypeScript, Java.
- **CS degree:** Yes. Major: Software Engineering.
- **Years of experience:** 0-3 / Entry Level
- **Non-compete:** No (length: 0 months)
- **GitHub username:** edwarddgao
- **Workday password:** Agdrawde1234!@#$
- **Alphabet/Waymo employee:** Never worked at Alphabet
- **Protected individual (Immigration Act):** None of the above
- **H-1B status:** No. Citizenship: Canada. Permanent US resident: No.
- **Export licensing country:** Canada
- **Government employee / family of govt official:** No
- **Enlisted/Reserves/National Guard:** No
- **BrightHire consent / data retention / background check:** Yes

## Workflow

### LinkedIn URL Resolution (if URL contains linkedin.com/jobs)

If your assigned URL is a LinkedIn job page, resolve it to the external career page first:

1. Navigate the tab to the LinkedIn URL
2. Run this JS to redirect in the same tab:
```javascript
(() => {
  const links = [...document.querySelectorAll('a')];
  const applyLink = links.find(a => a.textContent.trim().startsWith('Apply'));
  if (applyLink) {
    applyLink.target = '_self';
    applyLink.click();
    return 'Clicked apply link';
  }
  return 'No apply link found';
})()
```
3. Wait 3-4 seconds for the redirect to the external career page
4. If the page is still on LinkedIn (redirect failed), or the Apply button says "Easy Apply" (no external link icon), report STATUS: BLOCKED — LinkedIn Easy Apply / no external redirect
5. Once on the external career page, proceed with the normal workflow below

### Application Form

For each page/step of the application:

1. Screenshot to see current state
2. **FIRST CHECK:** If the Simplify panel shows "You applied to this job on [date]", report STATUS: ALREADY_APPLIED immediately and stop. Do not fill any fields.
3. Click the Simplify green "S" icon (top-right), then "Autofill this page", wait for "Autofill complete!"
4. Close Simplify panel (click X)
5. Click Next/Submit IMMEDIATELY — do NOT scroll through and review fields
6. If the page advances → great, repeat from step 1 on the new page
7. If an **error banner** appears at the top (e.g. "Errors Found"), read the listed errors. Each error is a clickable anchor link — click it to jump directly to the missing field, fill it, then click Next/Submit again
8. Repeat until all steps are done

**Key principle:** Let the form's own validation tell you what's missing. Never waste turns scrolling through a page to manually review fields. Autofill → Next → fix only what the error banner reports.

## Essay / Open-Ended Questions

Before filling any essay field, query the application count:

```bash
sqlite3 /Users/edwarddgao/just-apply/jobs.db "SELECT COUNT(*) FROM applications"
```

Then for ALL required essay/open-ended fields, use this response (replacing N with the count):

`Hi! This is application #N submitted fully autonomously by a system Edward built using Claude Code. It uses a Python orchestrator that spawns concurrent AI agents to navigate career pages and fill out applications. See it in action: https://youtu.be/MiDGBzrxSNk?si=C9HVTmRYluw_w2gM — if you're interested in someone who builds things like this, reach out at edwarddgao@gmail.com.`

Do NOT write custom answers from the resume or any other source. Just paste the default and move on. Skip optional essay fields entirely.

## Browser Notes

- Greenhouse forms use cross-origin iframe (id="grnhse_iframe") — use visual clicks, not JS
- Custom dropdowns: click to open, click the option
- Close Simplify panel before clicking Next/Submit (it overlaps buttons). On Workday, the panel does NOT block Next/Submit — just click through if the X button is unresponsive.
- **FILE UPLOADS:** You CANNOT interact with native OS file pickers. Resume/cover letter uploads MUST be handled by Simplify's autofill. If Simplify fails to upload the resume and the Resume/CV field shows "Attach" buttons instead of a filename, report STATUS: BLOCKED immediately. Do NOT waste time trying to click Attach or use workarounds.
- **EMAIL VERIFICATION:** Some ATS platforms (e.g. Waymo/Clinch Talent) require entering a verification code sent via email after form submission. You have access to Gmail MCP tools — use `gmail_search_messages` to find the code, then enter it on the page. This is NOT a blocker.

## Known Simplify Gaps

### Fix if spotted in error banner or while filling nearby fields
- **Sponsorship/work auth**: Simplify sometimes sets wrong. Correct values: sponsorship=Yes, US work auth=No, "legally employable"=Yes.
- **Essay fields**: Simplify may dump resume text. Clear (cmd+a Delete) before typing default response.
- **GitHub username**: Simplify fills full URL. Correct to just "edwarddgao" if field asks for username.
- **Security clearance**: Simplify sometimes sets to "Yes". Correct: No (Canadian citizen).

### Fields Simplify leaves empty (fill manually)
- "How did you hear" → "Job Board"
- Start date → "As soon as possible". Graduation date → "April 2025". Graduation year radio → pick closest 2025 option.
- SMS consent → "No"
- Preferred location → role's city
- GPA → 3.8
- Salary expectations → 0 (use JS for number fields)
- Workday CC-305 name → "Edward Gao"
- Current Company (Ashby/Lever) → "Amazon"
- Ashby location dropdown → retype and select (Simplify doesn't confirm selection)
- Ashby toggle/radio fields → fill manually (1 click each)
- Greenhouse privacy/accuracy dropdowns → "Yes" / "I acknowledge"
- Greenhouse degree multi-select → click field, select "Bachelor's"

### Platform interaction
- **Greenhouse dropdowns**: use ref click → type to filter → Enter. Coordinate clicks don't work.
- **Ashby combobox**: type to filter → Enter.
- **Simplify panel blocking buttons**: click through it or close. On Workday, panel does NOT block Next.
- **Simplify hangs ("Filling first name..." or "Fetching AI answers")**: click form field, type a character, click "Skip to next input".
- **EU Greenhouse**: scroll to "Apply for this job" BEFORE autofill.
- **Large dropdowns (3000+ options)**: use JS to set value.
- **reCAPTCHA**: NOT a blocker. v3 passes automatically. Solve visual challenges if they appear.
- **Greenhouse email verification**: search Gmail for "security code newer_than:10m" from no-reply@us.greenhouse-mail.io.
- **Waymo (Clinch Talent)**: requires email verification code after submission. Search Gmail. Also check certification checkbox before submitting.

### Immediate BLOCKED conditions
- No Simplify autofill available (custom career portal)
- File upload beyond resume (transcript, cover letter) that Simplify didn't handle
- Resume/CV still shows "Attach" after autofill (Greenhouse inline)
- Cross-origin Greenhouse iframe with unfilled required dropdowns (after 2-3 attempts)
- Reapply blocks (Ashby 180-day, Lever 6-month)
- iCIMS login pages
- Lever hCaptcha (2 failed submit attempts)
- Workday "doesn't exist" page (real 404 — job removed)
- Extension disconnection → report ERROR immediately. Do NOT restart Chrome or call tabs_context_mcp.

## Reporting

Your final message MUST start with a status line:

```
STATUS: SUBMITTED
STATUS: ALREADY_APPLIED
STATUS: BLOCKED — [reason]
STATUS: ERROR — [reason]
```

After the status line, include a one-line summary of what happened. If you encountered something unexpected not covered above, add: `NEW OBSERVATION: [description]`
