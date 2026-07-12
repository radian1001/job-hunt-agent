# job-hunt-agent

Multi-provider job scanner, application drafter, and pipeline tracker powered by
Claude Code, TinyFish MCP, SQLite, and Telegram.

## What it does
- Every day at 9:00 AM IST, `/job-scan` discovers roles from all enabled providers
  (favorite-company careers pages in `config/favorites.txt`, search queries in
  `config/searches.txt`, job boards in `config/providers.json`), dedupes by
  company+title+location+source fingerprint, scores new roles against
  `config/resume.md` with a ✓/✗ explanation each, stores everything in
  `state/jobhunt.db`, and Telegrams a digest (scanned totals, new jobs, top matches).
- On demand, `/draft-application <N|URL>` reuses the cached JD, writes a tailored
  `resume_<company>.md`, `cover_letter_<company>.md`, and `application_info.txt`
  into `applications/<company>-<date>/`, and marks the job **Drafted**.
- `/track` updates application status: Drafted → Applied → Interview → Rejected/Offer → Accepted.
- Weekly: `/discover-startups` (Mon 9:30) finds new companies and adds them to future
  scans; `/weekly-report` (Sun 18:00) Telegrams analytics — jobs scanned, applications,
  interview rate, top requested skills, newly discovered companies.
- **You review and submit every application manually. Nothing auto-applies.**

## One-time setup
1. Fill `config/resume.md` with your resume.
2. Put 15-30 careers-page URLs in `config/favorites.txt` and your search queries
   in `config/searches.txt`.
3. Copy `config/telegram.json.example` to `config/telegram.json` and fill in your
   bot token (from @BotFather) and chat id.
4. `claude mcp add --transport http tinyfish https://agent.tinyfish.ai/mcp` then
   complete the browser OAuth once.
5. `python scripts\db.py init` to create the database.
6. Run `scripts\register-task.ps1` to schedule the daily scan + weekly jobs.

> **Unattended-run note:** scheduled runs process untrusted web content (careers pages,
> search results) with a scoped tool allowlist. The allowlist reduces, but does not
> eliminate, what a malicious page could make the agent execute — `python`/`powershell`
> grants still allow arbitrary code. Accepted trade-off for hands-off operation; review
> `logs\` periodically.

## Manual runs
- Scan now: `claude -p "/job-scan"` from this directory (or `schtasks /run /tn JobHuntScan`).
- Draft an application: `claude -p "/draft-application 2"` (role #2 from today's digest).
- Update status: `claude -p "/track razorpay applied"`.
- Pipeline view: `python scripts\db.py track --list`
- Analytics: `python scripts\db.py stats --since 7`
- Reply from your phone: send the bot "apply to #N" — the JobHuntPoller task (every 5 min, registered by scripts\register-poller.ps1) drafts it automatically.
