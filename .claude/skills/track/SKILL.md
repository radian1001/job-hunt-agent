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

   Match the user's company name (case-insensitive substring of the `company` field)
   or, for `#N`, resolve via the newest digest in `digests/` (its `Fingerprint:` line).
   If nothing matches, list the tracked companies and stop. If several match, ask
   which one (or in headless mode, pick the most recently updated and say so).

2. Map the user's word to the exact status value: applied→Applied,
   interview/interviewing→Interview, rejected/rejection→Rejected, offer→Offer,
   accepted/joined→Accepted, drafted→Drafted. Anything else: list valid statuses
   and stop.

3. Update:

       python scripts/db.py track --fingerprint <fp> --status <Status> --notes "<any extra context the user gave>"

4. Confirm in one line: "<Company> — <Role>: <old status> → <new status>".

## Showing the pipeline

Run `python scripts/db.py track --list` and render a compact table: Company | Role |
Status | Last updated. Group counts at the top (e.g. "2 Drafted, 3 Applied,
1 Interview"). If the user asked from Telegram context, also send it via
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/send-telegram.ps1 -Message "<text>"`.
