---
name: track
description: Update or view job application status (Drafted, Applied, Interview, Rejected, Offer, Accepted). Use when the user says "track", "mark <company> applied", "I got an interview at X", "rejected by X", "offer from X", "show my pipeline", or "application status".
---

# Application Tracker

Argument forms:
- `<company or #N> <status>` — e.g. "razorpay applied", "#2 interview", "acme offer"
- `list` (or no argument) — show the pipeline

## Updating a status

1. Resolve the application:

       python scripts/db.py track --list

   Match the user's company name (case-insensitive substring of the `company` field).
   Note the matched row's current `status` — you need it for the confirmation line in
   step 4. For `#N`, open the newest digest in `digests/` (filenames sort
   chronologically), find that digest's `## #N — <Company> — <Role>` heading, and take
   its `Fingerprint:` line; then find the `track --list` row with that fingerprint. If
   the `#N` job has no row in `track --list` (never drafted), say "role #N hasn't been
   drafted yet — run /draft-application N first" and stop.
   If nothing matches, list the tracked companies and stop. If several match, ask
   which one (or in headless mode, pick the most recently updated and say so).

2. Map the user's word (case-insensitive) to the exact status value: applied→Applied,
   interview/interviewing→Interview, rejected/rejection→Rejected, offer→Offer,
   accepted/joined→Accepted, drafted→Drafted. Anything else: list valid statuses
   and stop.

3. Update. If the user gave EXTRA context beyond the status word, pass it as notes;
   otherwise OMIT `--notes` entirely (passing an empty `--notes ""` would overwrite
   any existing note — the flag must be absent to preserve it):

       python scripts/db.py track --fingerprint <fp> --status <Status>
       # only when the user added context, e.g. "rejected after HR call":
       python scripts/db.py track --fingerprint <fp> --status <Status> --notes "after HR call"

4. Confirm in one line, using the current status you noted in step 1:
   "<Company> — <Role>: <old status> → <new status>".

## Showing the pipeline

Run `python scripts/db.py track --list` and render a compact table: Company | Role |
Status | Last updated. Group counts at the top (e.g. "2 Drafted, 3 Applied,
1 Interview"). If the user asked from Telegram context, also send it via
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/send-telegram.ps1 -Message "<text>"`.
