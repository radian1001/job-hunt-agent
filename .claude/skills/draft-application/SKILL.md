---
name: draft-application
description: Draft a tailored application for a role from the daily job-scan digest - tailored resume, cover letter, and application info saved to a folder, and mark it Drafted in the tracker. Use when the user says "apply to #N", "draft application N", or passes a job URL directly.
---

# Application Drafter

Argument: either a role number `N` (from the most recent digest in `digests/`) or a
direct job-posting URL.

## Steps

1. **Resolve the role.**
   - If given a number N: read the newest file in `digests/` (sort by filename, they
     are YYYY-MM-DD.md), find the `## #N — <Company> — <Role>` section, take its
     `Fingerprint:` and `URL:` lines.
   - If given a URL: use it directly; company name comes from the JD page. Register
     it so the tracker works: build canonical job JSON per `docs/job-schema.md`,
     write to `state/tmp/job-adhoc.json`, run
     `python scripts/db.py add-job --file state/tmp/job-adhoc.json`, and use the
     returned fingerprint.
   - If N doesn't exist in the digest, tell the user which numbers are available and stop.

2. **Get the full JD — cache first, network second.**

       python scripts/db.py get-jd --fingerprint <fp>

   Exit code 0: use the printed markdown — do NOT re-fetch.
   Exit code 3 (no cached JD): fetch the URL with the TinyFish `fetch_content` tool,
   save to `state/tmp/jd-<fp>.md`, then
   `python scripts/db.py cache-jd --fingerprint <fp> --file state/tmp/jd-<fp>.md`
   and use it. If the fetch fails, report the failure via Telegram and stop — do not
   draft from memory.

3. **Make the output folder**: `applications/<company-slug>-<YYYY-MM-DD>/` where
   company-slug is the lowercase company name with spaces/punctuation replaced by
   hyphens (e.g. `razorpay-2026-07-09`).

4. **Write `resume_<company-slug>.md`**: the user's resume from `config/resume.md`,
   with experience bullets REWORDED to mirror the JD's language and emphasized skills.
   - HARD RULE: every bullet must be truthful. Rephrase, reorder, and re-emphasize
     only. NEVER invent experience, projects, employers, titles, dates, or skills not
     present in `config/resume.md`.
   - Put the most JD-relevant bullets first within each job.

5. **Write `cover_letter_<company-slug>.md`**, one page:
   - Opening: the specific reason THIS role fits (name something concrete from the JD
     — not generic enthusiasm).
   - Paragraph 1: most relevant experience, mapped to the JD's top requirements.
   - Paragraph 2: why this company specifically.
   - Close: clear ask for a conversation.

6. **Write `application_info.txt`**:
   - Application URL (or careers email if that's the mechanism)
   - Any hiring manager / recruiter / "for questions contact X" name found in the JD
   - Role title, location, fingerprint, and the date drafted
   - Line: "SUBMIT MANUALLY — this agent never submits applications."

7. **Track it**:

       python scripts/db.py track --fingerprint <fp> --status Drafted --folder "applications/<folder>"

8. **Notify**: send via
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/send-telegram.ps1 -Message "<text>"`
   the message: "Drafted: <Company> — <Role>. Files in applications/<folder>/.
   Review and submit manually, then run: claude -p \"/track <company> applied\""

## Rules
- NEVER submit, fill, or interact with any application form. Files only.
