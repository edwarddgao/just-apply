---
name: apply-to-job
description: Fill out a job application form on a browser tab using Simplify autofill
---

# Job Application Form Filler

Your assignment (tab ID, URL, company, role) is provided in the agent prompt that loaded this skill.

## Setup

Read these files before starting:
- /Users/edwarddgao/just-apply/resume/edward_gao_resume.tex (candidate resume)
- /Users/edwarddgao/just-apply/form-answers.md (known form field answers)

## Workflow

For each page/step of the application:

1. Screenshot to see current state
2. **FIRST CHECK:** If the Simplify panel shows "You applied to this job on [date]", report STATUS: ALREADY_APPLIED immediately and stop. Do not fill any fields.
3. Click the Simplify green "S" icon (top-right), then "Autofill this page", wait for "Autofill complete!"
4. Close Simplify panel (click X)
5. Only fill REQUIRED fields that Simplify missed — skip all optional fields
6. Click Next/Submit immediately — don't review every field, just ensure required ones aren't empty
7. Repeat for each step

Move fast. For basic profile fields (name, email, phone, address, education, work history, yes/no questions), fill them from the resume and form-answers.md.

## Essay / Open-Ended Questions

For ALL required essay/open-ended fields, use this default response:

`This is an automated application submitted via Claude Code on behalf of Edward. For any specific questions, please contact him directly at edwarddgao@gmail.com`

Do NOT write custom answers from the resume or any other source. Just paste the default and move on. Skip optional essay fields entirely.

## Browser Notes

- Greenhouse forms use cross-origin iframe (id="grnhse_iframe") — use visual clicks, not JS
- Custom dropdowns: click to open, click the option
- Close Simplify panel before clicking Next/Submit (it overlaps buttons)
- **FILE UPLOADS:** You CANNOT interact with native OS file pickers. Resume/cover letter uploads MUST be handled by Simplify's autofill. If Simplify fails to upload the resume and the Resume/CV field shows "Attach" buttons instead of a filename, report STATUS: BLOCKED immediately. Do NOT waste time trying to click Attach or use workarounds.

## Known Simplify Gaps

These are patterns observed from past runs. For each one you encounter, report whether it was CONFIRMED or CONTRADICTED in your skill audit (see reporting section below).

1. **Sponsorship dropdown** ("Do you require sponsorship...") — often NOT autofilled, always check and set to "Yes" for US roles. For Canadian roles, set to "No" (Canadian citizen).
2. **"How did you hear" dropdown** — Simplify may leave empty, select "Job Board" or closest option.
3. **"Ideal start date" on Ashby** — Simplify can't match, select "As soon as possible".
4. **SMS/text messaging consent** — Simplify skips it, select "No".
5. **Essay/open-ended fields** — Simplify sometimes dumps raw resume text into them. Clear with cmd+a then Delete before typing the real answer.
6. **reCAPTCHA is NOT a blocker** — invisible reCAPTCHA v3 passes automatically when you click Submit. If a visual challenge appears, solve it. Never report CAPTCHA as BLOCKED.
7. **Inline Greenhouse forms** — some embed on the company site rather than boards.greenhouse.io. Simplify still works on these.
8. **Sponsorship set to "No" on Ashby** — Simplify sets visa sponsorship to "No" on some Ashby forms. Always verify and flip to "Yes" for US roles.
9. **Ashby 180-day reapply block** — only surfaces at submit time, not pre-emptively.
10. **Custom career forms without Simplify** — if Simplify autofill is not available, report STATUS: BLOCKED immediately. Do not attempt to fill the entire form manually.
11. **Security clearance questions** (active clearance + eligibility) — Simplify misses these. Answer No/No (Canadian citizen, no US clearance).
12. **Large dropdowns** (3000+ options, e.g. university selects) — use JS to set the value, don't scroll visually.
13. **"Preferred location" textareas** — Simplify often misses these. Fill with the role's city.
14. **File upload fields beyond resume** (transcript, cover letter) — if Simplify didn't handle the upload, report STATUS: BLOCKED immediately. Do not waste tool uses trying workarounds.
15. **Lever "start date" free-text field** — Simplify leaves blank. Fill with "Immediately" or "As soon as possible".
16. **GPA field on Ashby** — Simplify leaves blank. Fill with 3.8.
17. **Very long forms (50+ fields, multiple pages beyond 3)** — if the form is excessively long or complex, report STATUS: BLOCKED immediately. Do not spend 50+ tool uses on a single form.
18. **EU Greenhouse domain** (`job-boards.eu.greenhouse.io`) — Simplify may hang on "Filling first name..." indefinitely. Fix: manually click the first form field and type a character to unblock Simplify.
19. **"Graduation date" free-text on Lever** — Simplify leaves blank. Fill with "April 2025" (McMaster Class of 2025).
20. **US work authorization set to "Yes"** — Simplify often incorrectly sets "Do you have unrestricted right to work in the US?" to "Yes". Always verify and correct to "No" (Canadian citizen needing sponsorship).

## Reporting (CRITICAL)

Your final message MUST follow this exact structure:

### 1. Status Line (FIRST LINE)

```
STATUS: SUBMITTED
STATUS: ALREADY_APPLIED
STATUS: BLOCKED — [reason]
STATUS: ERROR — [reason]
```

### 2. Summary

- **Tab ID:** [tab ID]
- **Company & Role:** [what you applied to]
- **What was completed:** [fields filled, pages progressed]
- **What remains:** [unfilled required fields, unanswered questions]

### 3. Skill Audit

For each Known Simplify Gap you encountered, report its number and result:

```
SKILL AUDIT:
- Gap #1 (Sponsorship dropdown): CONFIRMED — was empty, set to Yes
- Gap #4 (SMS consent): CONFIRMED — was missing, set to No
- Gap #8 (Sponsorship No on Ashby): CONTRADICTED — Simplify correctly set to Yes
- Gap #12 (Large dropdowns): N/A — not encountered
```

Only report gaps you actually encountered (CONFIRMED/CONTRADICTED). Skip gaps that were N/A unless you want to note something.

If you encountered something NEW not covered by any gap, report it:

```
NEW OBSERVATION: [description of what happened, what you did, how many tool uses it cost]
```

### 4. Tool Use Breakdown

```
TOOL USES: [total count]
- Navigation/screenshots: [count]
- Filling fields: [count]
- Fighting issues: [count] — [what the issue was]
```

### 5. Efficiency

Every tool call costs time and money. Minimize tool uses while still submitting successfully. If you spent >5 tool uses on any single issue, explain why and suggest how to avoid it next time.

NEVER return silently. ALWAYS include the full report even if everything went perfectly.
