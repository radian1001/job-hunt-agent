---
name: job-scan
description: Daily job scan - discover roles from all enabled providers, dedupe and store in SQLite, score new roles against my resume with explanations, and Telegram a digest. Use when the user says "job scan", "scan jobs", "run the daily scan", or when invoked headlessly on schedule.
---

# Daily Job Scan

Work from the project root (the directory containing `config/`). Today's date in
YYYY-MM-DD (IST) is needed throughout — get it from your environment context.
The pipeline is: Discovery → Extraction → Normalization → Storage → Ranking → Notification.
SQLite (`scripts/db.py`) is the source of truth; the digest markdown is a report for humans.

## 1. Read inputs
- `config/resume.md` — if it still contains "(paste here)" placeholders, STOP: send a
  Telegram message via the script in step 6 saying "job-scan aborted: config/resume.md
  is not filled in" and exit.
- `config/providers.json` — the provider registry. Iterate ONLY entries with
  `"enabled": true`.
- `config/favorites.txt` and `config/searches.txt` — inputs for the careers_page /
  ats_pattern and search providers. Skip blank lines and `#` comments.

## 2. Discovery + Extraction (per enabled provider)
For each enabled provider, follow its `description`:
- `careers_page` / `ats_pattern` kinds: fetch each favorites.txt URL with the TinyFish
  `fetch_content` tool; extract every individual posting (title + absolute URL).
- `search` kind: run each searches.txt query (plus the provider's `query_suffix`)
  through the TinyFish `search` tool; collect result links that are individual job
  postings. After processing each query, log it:
  `python scripts/db.py log-search --provider <id> --query "<q>" --results <found> --new <new>`
- `board_api` / `directory` kinds: fetch the provider's `entry_url` and extract
  postings per its description.
If one page/query fails, note it and continue — never abort the whole scan for one
bad source. Cap total posting-detail fetches at 25 per run to bound cost.

## 3. Normalization + Storage (dedup happens here)
For each extracted posting, build canonical job JSON per `docs/job-schema.md`
(set `source` = the provider id; include `company_info` with whatever the page
states — funding stage, size, industry, remote policy, product-company flag).
Write it to `state/tmp/job-<n>.json`, then:

    python scripts/db.py add-job --file state/tmp/job-<n>.json

The output says `"new": true|false` with the fingerprint. `new: false` = already
seen (company+title+location+source fingerprint) — skip it. NEVER dedupe by URL
or by your own judgment; the fingerprint is the only identity.

## 4. Ranking (new jobs only)
For each `new: true` job: fetch its posting URL with `fetch_content` to get the full
JD, cache it —

    python scripts/db.py cache-jd --fingerprint <fp> --file state/tmp/jd-<fp>.md

— then score it per `scoring.md` (in this skill's folder) and record via
`record-score`. Every score MUST include the matched/missing keyword explanation
and recommendation band.

## 5. Digest (human report)
Write `digests/<today>.md` with ALL new roles ranked by total score, using exactly
this per-role format (the drafter parses the Fingerprint line):

    ## #1 — <Company> — <Role Title>
    Score: <n>/100 — <recommendation>
    Fingerprint: <fp>
    Location: <location / remote policy>
    Stack: <comma-separated>
    URL: <absolute posting URL>
    [+] <matched keyword> [+] ...
    [-] <missing keyword> [-] ...
    Why it fits: <one line>

## 6. Notification (Telegram)
Send via:

    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/send-telegram.ps1 -Message "<text>"

Under 4000 characters, format:

    Job scan <today>
    Scanned: <total postings seen> across <P> providers | New: <N>
    New companies this week: <count from python scripts/db.py stats --since 7>
    Trend: top skills this week: <top 3 from stats top_skills>

    #1 | <Company> | <Role> | <Location> | <score> <recommendation>
    Why: <one line>
    <URL>

    ... (through #5)

    Reply 'apply to #N' or run: claude -p "/draft-application N"

If there are zero new roles, still send: "Job scan <today>: no new roles
(<total> postings checked across <P> providers)." Append failures at the end
("(2 sources failed: <domains>)").

## Rules
- NEVER apply to anything or fill any web form. Scan and report only.
- Never invent postings; only report roles actually present on fetched pages/results.
- Clean up `state/tmp/` job/score files at the end of the run.
