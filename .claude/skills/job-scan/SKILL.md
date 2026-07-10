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

## 2. Discovery + Extraction (per enabled provider) — build the candidate list
For each enabled provider, follow its `description`. This stage only LISTS postings
(cheap); it does not persist or score anything yet:
- `careers_page` / `ats_pattern` kinds: fetch each favorites.txt URL with the TinyFish
  `fetch_content` tool; extract every individual posting (title + absolute URL).
- `search` kind: run each searches.txt query (plus the provider's `query_suffix`)
  through the TinyFish `search` tool; collect result links that are individual job
  postings. After processing each query, log it:
  `python scripts/db.py log-search --provider <id> --query "<q>" --results <found> --new <new>`
  (report `--new` after Section 3-4 finishes, as the count of these results that
  turned out to be new-and-scored.)
- `board_api` / `directory` kinds: fetch the provider's `entry_url` and extract
  postings per its description.
If one page/query fails, note it and continue — never abort the whole scan for one
bad source. Collect all candidates into one list; remember the total for the digest's
"scanned" count.

## 3+4. Persist, dedup, and rank — ONE loop, capped at 25 NEW jobs
Process candidates one at a time. Persistence and ranking happen together so a job is
only ever recorded as "seen" once it has actually been scored — this guarantees a
posting that doesn't fit in this run's budget is simply re-discovered and scored on a
future run, never permanently lost.

For each candidate, until you have scored **25 NEW jobs this run** (the cost cap —
stop the loop once you hit it and leave the rest for a future run):

1. Build canonical job JSON per `docs/job-schema.md` (set `source` = the provider id;
   include `company_info` with whatever the page states — funding stage, size,
   industry, remote policy, product-company flag). Write to `state/tmp/job-<n>.json`.
2. `python scripts/db.py add-job --file state/tmp/job-<n>.json` — the output says
   `"new": true|false` with the fingerprint. `new: false` = already seen and scored on
   a prior run — skip to the next candidate (do NOT count it against the 25 cap).
   NEVER dedupe by URL or by your own judgment; the fingerprint is the only identity.
3. On `new: true`: fetch the posting URL with `fetch_content` to get the full JD,
   cache it — `python scripts/db.py cache-jd --fingerprint <fp> --file state/tmp/jd-<fp>.md` —
   then score it per `scoring.md` (in this skill's folder) and record via `record-score`.
   Every score MUST include the matched/missing keyword explanation and recommendation
   band. This counts as one of the 25.

Because `add-job` is only ever called at the moment a job is about to be scored,
"seen" and "scored" stay in lockstep — there are no seen-but-unscored orphans.

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
- Clean up scratch files in `state/tmp/` at the end of the run — the job JSON
  (`job-*.json`), the JD markdown (`jd-*.md`), and the score JSON (`score-*.json`).
  The cached JD lives in the DB, so the tmp copy is safe to delete.
