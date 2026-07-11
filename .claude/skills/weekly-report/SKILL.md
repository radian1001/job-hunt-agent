---
name: weekly-report
description: Weekly job-hunt analytics - jobs scanned, applications by status, interview rate, top requested skills, newly discovered companies. Use when the user says "weekly report", "job hunt analytics", "how's my pipeline", or when invoked headlessly on the weekly schedule.
---

# Weekly Report

Work from the project root. All numbers come from the database — do not estimate.

## Steps

1. **Pull the data:**

       python scripts/db.py stats --since 7
       python scripts/db.py track --list

2. **Write `reports/weekly-<today>.md`:**

       # Weekly Job Hunt Report — <today>

       ## Scanning
       - New jobs found: <new_jobs>
       - Searches run: <searches_run> (<results_total> raw results)
       - New companies discovered: <len(new_companies)> — <names>

       ## Pipeline
       | Status | Count |
       |--------|-------|
       (one row per status from applications, including zeros)
       - Interview rate: <interview_rate as percentage> (interviews+offers+accepted / submitted)

       ## Market signal
       - Top requested skills this week: <top_skills as "skill (count)" list>
       - Gap note: skills appearing in top_skills but weak/absent in config/resume.md
         (one honest line — this is the "what the market wants that I lack" signal).

       ## This week's applications
       (from track --list: company — role — status — last updated)

3. **Telegram the summary** (under 4000 chars) via
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/send-telegram.ps1 -Message "<text>"`:

       Weekly report <today>
       Jobs: <new_jobs> new | Searches: <searches_run>
       Pipeline: <e.g. 2 Drafted, 3 Applied, 1 Interview> | Interview rate: <pct>
       Top skills: <top 5, comma-separated>
       New companies: <count> (<first few names>)
       Full report: reports/weekly-<today>.md
