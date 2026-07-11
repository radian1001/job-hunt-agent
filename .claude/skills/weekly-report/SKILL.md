---
name: weekly-report
description: Weekly job-hunt analytics - jobs scanned, applications by status, interview rate, top requested skills, newly discovered companies. Use when the user says "weekly report", "job hunt analytics", "how's my pipeline", or when invoked headlessly on the weekly schedule.
---

# Weekly Report

Work from the project root. All numbers come from the database — do not estimate.
`<today>` everywhere below means the current date formatted exactly `YYYY-MM-DD`
(e.g. `2026-07-11`) — never a locale-dependent rendering.

## Steps

1. **Pull the data:**

       python scripts/db.py stats --since 7
       python scripts/db.py track --list

   If either command errors or prints something that is not valid JSON, STOP:
   send a Telegram message "weekly-report aborted: db.py failed — <error>" and
   exit. Never fill in a number the database did not produce.

2. **Write `reports/weekly-<today>.md`:**

       # Weekly Job Hunt Report — <today>

       ## Scanning
       - New jobs found: <new_jobs>
       - Searches run: <searches_run> (<results_total> raw results)
       - New companies discovered: <len(new_companies)> — <names>

       ## Pipeline
       | Status | Count |
       |--------|-------|
       (exactly six rows, in this order, taken from the stats `applications`
       object which always contains all six keys: Drafted, Applied, Interview,
       Rejected, Offer, Accepted — include zero counts)
       - Interview rate: <interview_rate as percentage> (interviews+offers+accepted
         / submitted, where submitted = Applied+Interview+Rejected+Offer+Accepted;
         Drafted is not submitted — this is how db.py computes interview_rate,
         so just render the stats value as a percentage)

       ## Market signal
       - Top requested skills this week: <top_skills as "skill (count)" list>
       - Gap note: skills appearing in top_skills but weak/absent in config/resume.md
         (one honest line — this is the "what the market wants that I lack" signal).

       ## This week's applications
       (from track --list: company — role — status — last updated;
        if track --list is empty, write the single line "None this week."
        — never omit this section)

3. **Telegram the summary** — keep it under 4000 characters: if the composed
   message would exceed that, drop company names first, then trim the skills
   list to top 3 (the send script also hard-truncates at 4000 as a backstop).
   Send via
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/send-telegram.ps1 -Message "<text>"`:

       Weekly report <today>
       Jobs: <new_jobs> new | Searches: <searches_run>
       Pipeline: <e.g. 2 Drafted, 3 Applied, 1 Interview> | Interview rate: <pct>
       Top skills: <top 5, comma-separated>
       New companies: <count> (<first few names>)
       Full report: reports/weekly-<today>.md
