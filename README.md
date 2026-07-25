# job-hunt-agent

An autonomous job-hunt pipeline that runs on your own Windows laptop: it scans the
careers pages and job boards **you** choose every morning, scores each new role
against **your** resume with an explained ✓/✗ breakdown, messages the top matches to
your phone via Telegram, drafts a tailored resume + cover letter when you reply
`apply to #N`, and tracks your pipeline through to offer — all powered by
[Claude Code](https://claude.com/claude-code) skills, [TinyFish](https://tinyfish.ai)
web fetching, SQLite, and the Telegram Bot API.

**You review and submit every application manually. Nothing auto-applies — ever.**

## How it works

```
Windows Task Scheduler (daily 9:00, Mon 9:30, Sun 18:00, poller every 5 min)
        │
        ▼
Claude Code (headless `claude -p`, scoped tool allowlist)
  ├── reads your config:  favorites.txt · searches.txt · providers.json · resume.md
  ├── fetches the web:    TinyFish MCP (renders JS-heavy careers pages cleanly)
  ├── remembers:          scripts/db.py → state/jobhunt.db (SQLite, source of truth)
  │                       dedup fingerprint = sha256(company|title|location|source)
  └── notifies you:       scripts/send-telegram.ps1 → your Telegram bot
```

| Schedule | Skill | What happens |
|----------|-------|--------------|
| Daily 9:00 | `/job-scan` | Scans all enabled providers, dedupes, scores new roles 0-100 against your resume (keyword 30 / experience 20 / projects 15 / seniority 15 / location 10 / company 10), writes `digests/<date>.md`, Telegrams the top 5 with a one-line "why it fits" each |
| On reply | poller → `/draft-application N` | You reply `apply to #N` on Telegram → tailored `resume_*.md`, `cover_letter_*.md`, `application_info.txt` land in `applications/<company>-<date>/`, job marked **Drafted**. A hard traceability rule forbids the AI from inventing anything not in your real resume |
| Anytime | `/track` | `claude -p "/track <company> applied"` — moves status through Drafted → Applied → Interview → Rejected/Offer → Accepted |
| Mon 9:30 | `/discover-startups` | Finds new companies hiring your stack, stores funding/size/industry intel, auto-appends promising careers URLs to your favorites |
| Sun 18:00 | `/weekly-report` | Analytics: jobs scanned, pipeline counts, interview rate, top in-demand skills vs the gaps in your resume |

## Prerequisites

- Windows 10/11 (uses Task Scheduler + PowerShell 5.1 — both built in)
- [Claude Code](https://claude.com/claude-code) installed and logged in (`claude` on PATH) — a paid Claude plan; the scan/draft runs consume your plan's usage
- Python 3.10+ on PATH (`python --version`) — stdlib only, **no pip installs**
- A free [TinyFish](https://agent.tinyfish.ai) account (web search/fetch for agents — no card)
- Telegram on your phone

## Setup — every step

### 1. Clone and enter

```powershell
git clone https://github.com/<you>/job-hunt-agent.git
cd job-hunt-agent
```

### 2. Add YOUR data (placeholders → real files)

These three files are gitignored — your personal data never leaves your machine:

```powershell
copy config\favorites.txt.example config\favorites.txt    # then edit: 15-30 careers URLs you care about
copy config\searches.txt.example  config\searches.txt     # then edit: queries for your stack/level/location
notepad config\resume.md                                   # create it: paste your FULL resume as markdown
```

`config/resume.md` needs your real resume — summary, skills, every job with bullets,
projects, education. The scanner scores against it and the drafter rewrites it, so
the better it is, the better everything downstream is. Structure it like:

```markdown
# Resume — Your Name
## Summary
## Skills
## Experience
### Company — Title (dates, location, bullet points)
## Projects
## Education
```

### 3. Create your Telegram bot (~3 minutes)

1. In Telegram, message **@BotFather** → send `/newbot` → pick a name and username → copy the **bot token**.
2. Send your new bot any message (e.g. "hi") so it has something to read.
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser → find `"chat":{"id": <number>` → that number is your **chat id**.
4. Wire it up:

```powershell
copy config\telegram.json.example config\telegram.json
notepad config\telegram.json      # paste bot_token and chat_id
```

5. Test it — you should get a message on your phone:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\send-telegram.ps1 -Message "wiring works"
```

### 4. Connect TinyFish (web fetching)

```powershell
claude mcp add --transport http --scope user tinyfish https://agent.tinyfish.ai/mcp
```

Then run `claude` interactively in this folder, type `/mcp`, select `tinyfish`, and
complete the browser login once (sign up free at agent.tinyfish.ai first). Verify:

```powershell
claude mcp list      # tinyfish should say Connected
```

### 5. Initialize the database

```powershell
python scripts\db.py init
```

### 6. Schedule everything

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register-task.ps1     # daily scan + weekly discovery/report
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register-poller.ps1   # Telegram reply poller, every 5 min
```

This registers four Task Scheduler entries: `JobHuntScan` (daily 09:00),
`JobHuntDiscovery` (Mon 09:30), `JobHuntWeekly` (Sun 18:00), `JobHuntPoller`
(every 5 min). All are configured to run on battery and wake the laptop from sleep.

### 7. First run — don't wait for tomorrow

```powershell
claude -p "/job-scan"
```

Takes 10-20 minutes depending on how many sources you listed. Watch your phone.

## Daily use

- **Morning:** digest arrives on Telegram. Read the top 5.
- **Apply:** reply `apply to #2` to the bot (or run `claude -p "/draft-application 2"`).
  Within ~10 min you get "Drafted: ..." with a folder containing the tailored resume,
  cover letter, and the application URL.
- **Before submitting: READ THE DRAFTS.** The drafter is bound by a traceability rule
  (nothing not in your real resume), but you are the final quality gate — edit anything
  that doesn't sound like you, then submit at the URL yourself.
- **After submitting:** `claude -p "/track <company> applied"` (later: `interview`,
  `offer`, `rejected`, `accepted`) so Sunday's analytics stay honest.
- **Pipeline at a glance:** `python scripts\db.py track --list` · `python scripts\db.py stats --since 7`

## Things to know

- **Laptop must be on or asleep** at trigger time — the tasks wake it from sleep, but
  a powered-off machine can't wake itself. If a run is missed because the machine was
  off, it fires shortly after the next boot (the tasks use "start when available"), or
  you can hit Scan Now in the dashboard. Claude Code does NOT need to be open; the
  scheduler launches it.
- **Usage limits:** runs consume your Claude plan. If a run logs
  "You've hit your session limit", it resumes working after the reset time.
- **Logs** live in `logs\` (`scan.log`, `discovery.log`, `weekly.log`,
  `poller-error.log`, per-draft logs). First place to look if something seems dead.
- **Security:** scheduled runs process untrusted web content (careers pages, search
  results) with a scoped tool allowlist (see the `.cmd` wrappers). The allowlist
  reduces, but does not eliminate, what a malicious page could make the agent
  execute — the `python`/`powershell` grants still allow arbitrary code. That's an
  accepted trade-off for hands-off operation on a personal machine; review `logs\`
  periodically. Your `telegram.json`, `resume.md`, favorites/searches, database,
  digests, and drafted applications are all gitignored and stay local.
- **Add/remove job sources** by editing `config/providers.json` (Greenhouse, Lever,
  Ashby, RemoteOK, YC directory, Wellfound included; add others by appending an
  entry — no code changes needed) and your `favorites.txt` / `searches.txt`.

## Repo layout

```
.claude/skills/        the five agent skills (prose instructions Claude executes)
config/                your inputs (*.example are templates; real files gitignored)
docs/job-schema.md     the canonical job JSON contract
scripts/db.py          SQLite storage layer + CLI (jobs, dedup, JD cache, tracker, stats)
scripts/*.ps1|.cmd     Telegram send/poll, scheduler registration, run wrappers
scripts/test_*         test suites (python -m unittest / plain PowerShell)
digests/ reports/      generated human-readable outputs (gitignored)
applications/          drafted applications (gitignored)
state/                 SQLite DB + runtime state (gitignored)
```

## Credits

Workflow inspired by the "Find & Apply to Jobs Using AI Agents" pattern (TinyFish +
agent + Telegram). Built with Claude Code as the agent runtime instead of a separate
agent framework.

## Dashboard (recommended if your machine isn't always on)

Double-click `dashboard.cmd` (or run `python scripts\dashboard.py`) and open
http://127.0.0.1:8765. It shows every scored job with its match breakdown, and gives
you a "Scan for jobs now" button, a Draft button per job, and a status dropdown per
job, so you never need the terminal or Telegram to drive the pipeline. Reads the same
SQLite database and runs the same skills as the scheduled jobs.

Bound to 127.0.0.1 only: it exposes your job data and can launch local processes, so
it must never be put on a public interface.

Scheduled tasks are also set to "run as soon as possible after a missed start", so a
scan skipped because the laptop was off fires shortly after you next boot.
