---
name: discover-startups
description: Weekly startup discovery - find new companies hiring for my stack, store them with company intelligence, and add promising ones to the daily scan. Use when the user says "discover startups", "find new companies", or when invoked headlessly on the weekly schedule.
---

# Weekly Startup Discovery

Work from the project root. Goal: grow the company pool so daily scans keep
finding fresh roles.

## Steps

1. **Load the known-company list** so you don't re-discover:

       python scripts/db.py list-companies

2. **Search for new companies** using the TinyFish `run_big_search` tool
   (mode: standard). Sources, in order:
   - Each query in `config/searches.txt` rephrased for companies, e.g.
     "startups hiring <query> 2026".
   - Directory providers in `config/providers.json` with kind "directory"
     (fetch their entry_url with `fetch_content` even if disabled for daily
     scans — discovery-only use).
   - "layoffs.fyi still hiring" list.
   Log each query: `python scripts/db.py log-search --provider discovery --query "<q>" --results <found> --new <new companies>`

3. **For each candidate company NOT already known** (cap 10 per run): fetch its
   site/careers page with `fetch_content` and extract company intelligence —
   funding stage, company size, industry, remote policy, product-company flag,
   careers URL. Store only what pages actually state — OMIT any flag whose value
   the page doesn't support (an omitted flag stays unset in the DB; that is
   correct). Every value below is a placeholder, including the product flag —
   pass `--is-product 1` only if the page shows they build their own product,
   `--is-product 0` if it's a staffing/consultancy/services firm, and omit the
   flag entirely when you can't tell:

       python scripts/db.py upsert-company --name "<Name>" --careers-url "<url>" --source discovery --funding-stage "<stage>" --company-size "<size>" --industry "<ind>" --remote-policy "<policy>" --is-product <0 or 1, omit if unstated>

4. **Promote to the daily scan**: for each newly stored company whose careers URL
   renders postings, FIRST check the URL isn't already in the file
   (`grep -F "<careers_url>" config/favorites.txt` — skip if found, including
   manually-curated entries), then append a line to `config/favorites.txt`:

       <careers_url>  # auto-discovered <today>

5. **Notify** via
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/send-telegram.ps1 -Message "<text>"`:

       Startup discovery <today>
       Checked <N> candidates, added <M> new companies:
       - <Name> (<industry>, <funding_stage>) — <careers_url>
       ...
       They join tomorrow's 9 AM scan.

   If none were added: "Startup discovery <today>: no new companies found."

## Rules
- Never fabricate company intelligence — only store what a fetched page states.
- Never remove existing lines from config/favorites.txt; append only.
