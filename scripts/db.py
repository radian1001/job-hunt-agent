#!/usr/bin/env python3
"""job-hunt-agent storage layer. SQLite, stdlib only.

Source of truth for jobs, companies, dedup, JD cache, scores, applications,
and search history. Called by Claude Code skills as a CLI; JSON in/out.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("JOBHUNT_DB", os.path.join(ROOT, "state", "jobhunt.db"))

STATUSES = ("Drafted", "Applied", "Interview", "Rejected", "Offer", "Accepted")

ALLOWED_COMPANY_FIELDS = {
    "careers_url", "source", "funding_stage", "company_size",
    "industry", "remote_policy", "is_product_company", "is_favorite",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS Companies (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  slug TEXT NOT NULL,
  careers_url TEXT,
  source TEXT,
  funding_stage TEXT,
  company_size TEXT,
  industry TEXT,
  remote_policy TEXT,
  is_product_company INTEGER,
  is_favorite INTEGER NOT NULL DEFAULT 0,
  discovered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS Jobs (
  id INTEGER PRIMARY KEY,
  fingerprint TEXT NOT NULL UNIQUE,
  company_id INTEGER NOT NULL REFERENCES Companies(id),
  title TEXT NOT NULL,
  location TEXT,
  remote_policy TEXT,
  url TEXT,
  source TEXT NOT NULL,
  stack TEXT NOT NULL DEFAULT '[]',
  yoe_min REAL,
  yoe_max REAL,
  seniority TEXT,
  jd_markdown TEXT,
  jd_fetched_at TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS SeenJobs (
  fingerprint TEXT PRIMARY KEY,
  first_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS Applications (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL UNIQUE REFERENCES Jobs(id),
  status TEXT NOT NULL CHECK (status IN
    ('Drafted','Applied','Interview','Rejected','Offer','Accepted')),
  folder TEXT,
  notes TEXT,
  drafted_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ResumeScores (
  id INTEGER PRIMARY KEY,
  job_id INTEGER NOT NULL REFERENCES Jobs(id),
  total INTEGER NOT NULL,
  keyword_score INTEGER,
  project_score INTEGER,
  experience_score INTEGER,
  location_score INTEGER,
  seniority_score INTEGER,
  company_score INTEGER,
  semantic_score REAL,  -- reserved: future embedding-based similarity
  matched_keywords TEXT NOT NULL DEFAULT '[]',
  missing_keywords TEXT NOT NULL DEFAULT '[]',
  recommendation TEXT,
  explanation TEXT,
  scored_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS SearchHistory (
  id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL,
  query TEXT NOT NULL,
  results_count INTEGER NOT NULL DEFAULT 0,
  new_jobs_count INTEGER NOT NULL DEFAULT 0,
  run_at TEXT NOT NULL
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def make_fingerprint(company, title, location, source):
    raw = "|".join(norm(x) for x in (company, title, location, source))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def slugify(name):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (name or "").lower())).strip("-")


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


def upsert_company(con, name, **fields):
    """Returns (company_id, created). Non-None fields update existing rows."""
    fields = {k: v for k, v in fields.items() if k in ALLOWED_COMPANY_FIELDS}
    row = con.execute("SELECT id FROM Companies WHERE name = ?", (name,)).fetchone()
    if row:
        sets = {k: v for k, v in fields.items() if v is not None}
        if sets:
            con.execute(
                "UPDATE Companies SET " + ", ".join(f"{k} = ?" for k in sets) + " WHERE id = ?",
                (*sets.values(), row["id"]))
            con.commit()
        return row["id"], False
    cur = con.execute(
        "INSERT INTO Companies (name, slug, careers_url, source, funding_stage,"
        " company_size, industry, remote_policy, is_product_company, is_favorite,"
        " discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (name, slugify(name), fields.get("careers_url"), fields.get("source"),
         fields.get("funding_stage"), fields.get("company_size"), fields.get("industry"),
         fields.get("remote_policy"), fields.get("is_product_company"),
         fields.get("is_favorite") or 0, now()))
    con.commit()
    return cur.lastrowid, True


def add_job(con, job):
    """job = canonical job JSON dict. Returns {new, job_id, fingerprint, company_id}."""
    fp = make_fingerprint(job["company"], job["title"], job.get("location"), job["source"])
    company_id, _ = upsert_company(con, job["company"], **(job.get("company_info") or {}))
    ts = now()
    existing = con.execute("SELECT id FROM Jobs WHERE fingerprint = ?", (fp,)).fetchone()
    if existing:
        con.execute("UPDATE Jobs SET last_seen = ? WHERE id = ?", (ts, existing["id"]))
        con.commit()
        return {"new": False, "job_id": existing["id"], "fingerprint": fp,
                "company_id": company_id}
    con.execute("INSERT OR IGNORE INTO SeenJobs (fingerprint, first_seen) VALUES (?, ?)",
                (fp, ts))
    cur = con.execute(
        "INSERT INTO Jobs (fingerprint, company_id, title, location, remote_policy,"
        " url, source, stack, yoe_min, yoe_max, seniority, first_seen, last_seen)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fp, company_id, job["title"], job.get("location"), job.get("remote_policy"),
         job.get("url"), job["source"], json.dumps(job.get("stack") or []),
         job.get("yoe_min"), job.get("yoe_max"), job.get("seniority"), ts, ts))
    con.commit()
    return {"new": True, "job_id": cur.lastrowid, "fingerprint": fp,
            "company_id": company_id}


def cache_jd(con, fingerprint, markdown):
    cur = con.execute(
        "UPDATE Jobs SET jd_markdown = ?, jd_fetched_at = ? WHERE fingerprint = ?",
        (markdown, now(), fingerprint))
    con.commit()
    if cur.rowcount == 0:
        raise KeyError(f"no job with fingerprint {fingerprint}")


def get_jd(con, fingerprint):
    row = con.execute("SELECT jd_markdown FROM Jobs WHERE fingerprint = ?",
                      (fingerprint,)).fetchone()
    return row["jd_markdown"] if row else None


def get_job(con, fingerprint):
    """Full job row + company name, as a dict. None if the fingerprint is unknown."""
    row = con.execute(
        "SELECT j.fingerprint, j.title, j.location, j.remote_policy, j.url, j.source,"
        " j.stack, j.yoe_min, j.yoe_max, j.seniority, j.first_seen, j.last_seen,"
        " (j.jd_markdown IS NOT NULL) AS has_jd, c.name AS company, c.slug AS company_slug,"
        " c.industry, c.funding_stage, c.company_size"
        " FROM Jobs j JOIN Companies c ON c.id = j.company_id"
        " WHERE j.fingerprint = ?", (fingerprint,)).fetchone()
    if not row:
        return None
    job = dict(row)
    job["stack"] = json.loads(job["stack"] or "[]")
    return job


def list_jobs(con, limit=200):
    """Jobs joined with their latest score and application status, best score first.
    Powers the dashboard's job list."""
    rows = con.execute(
        "SELECT j.fingerprint, c.name AS company, j.title, j.location, j.remote_policy,"
        " j.url, j.source, j.stack, j.seniority, j.first_seen,"
        " (j.jd_markdown IS NOT NULL) AS has_jd,"
        " s.total, s.recommendation, s.matched_keywords, s.missing_keywords,"
        " a.status, a.folder, a.updated_at AS status_updated_at"
        " FROM Jobs j"
        " JOIN Companies c ON c.id = j.company_id"
        " LEFT JOIN Applications a ON a.job_id = j.id"
        " LEFT JOIN (SELECT job_id, MAX(id) AS max_id FROM ResumeScores GROUP BY job_id)"
        "   latest ON latest.job_id = j.id"
        " LEFT JOIN ResumeScores s ON s.id = latest.max_id"
        " ORDER BY COALESCE(s.total, -1) DESC, j.first_seen DESC LIMIT ?",
        (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for key in ("stack", "matched_keywords", "missing_keywords"):
            d[key] = json.loads(d[key] or "[]")
        out.append(d)
    return out


def keyword_gaps(con, min_score=45, limit=25):
    """Which skills keep showing up as MISSING across the roles worth applying to.

    Answers "what should I add to my resume next": counts each keyword once per
    job, only over jobs scoring at least min_score (ignoring roles that were
    never a fit anyway), and reports which companies wanted it. Keywords are
    grouped case-insensitively; the most common spelling is used for display.
    """
    rows = con.execute(
        "SELECT s.missing_keywords, s.total, c.name AS company, j.title"
        " FROM ResumeScores s"
        " JOIN (SELECT job_id, MAX(id) AS max_id FROM ResumeScores GROUP BY job_id)"
        "   latest ON latest.max_id = s.id"
        " JOIN Jobs j ON j.id = s.job_id"
        " JOIN Companies c ON c.id = j.company_id"
        " WHERE s.total >= ?", (min_score,)).fetchall()

    counts, spellings, wanted_by = Counter(), {}, {}
    for r in rows:
        seen = set()
        for raw in json.loads(r["missing_keywords"] or "[]"):
            kw = (raw or "").strip()
            if not kw:
                continue
            key = kw.lower()
            if key in seen:  # count a keyword once per job
                continue
            seen.add(key)
            counts[key] += 1
            spellings.setdefault(key, Counter())[kw] += 1
            wanted_by.setdefault(key, []).append(r["company"])

    out = []
    for key, n in counts.most_common(limit):
        out.append({
            "keyword": spellings[key].most_common(1)[0][0],
            "missing_in_jobs": n,
            "wanted_by": sorted(set(wanted_by[key]))[:6],
        })
    return {"jobs_considered": len(rows), "min_score": min_score, "gaps": out}


def record_score(con, fingerprint, score):
    job = con.execute("SELECT id FROM Jobs WHERE fingerprint = ?", (fingerprint,)).fetchone()
    if not job:
        raise KeyError(f"no job with fingerprint {fingerprint}")
    con.execute(
        "INSERT INTO ResumeScores (job_id, total, keyword_score, project_score,"
        " experience_score, location_score, seniority_score, company_score,"
        " semantic_score, matched_keywords, missing_keywords, recommendation,"
        " explanation, scored_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (job["id"], score["total"], score.get("keyword_score"), score.get("project_score"),
         score.get("experience_score"), score.get("location_score"),
         score.get("seniority_score"), score.get("company_score"),
         score.get("semantic_score"),
         json.dumps(score.get("matched_keywords") or []),
         json.dumps(score.get("missing_keywords") or []),
         score.get("recommendation"), score.get("explanation"), now()))
    con.commit()


def track(con, fingerprint, status, folder=None, notes=None):
    job = con.execute("SELECT id FROM Jobs WHERE fingerprint = ?", (fingerprint,)).fetchone()
    if not job:
        raise KeyError(f"no job with fingerprint {fingerprint}")
    ts = now()
    existing = con.execute("SELECT id FROM Applications WHERE job_id = ?",
                           (job["id"],)).fetchone()
    if existing:
        con.execute(
            "UPDATE Applications SET status = ?, updated_at = ?,"
            " folder = COALESCE(?, folder), notes = COALESCE(?, notes) WHERE id = ?",
            (status, ts, folder, notes, existing["id"]))
    else:
        con.execute(
            "INSERT INTO Applications (job_id, status, folder, notes, drafted_at,"
            " updated_at) VALUES (?,?,?,?,?,?)",
            (job["id"], status, folder, notes, ts, ts))
    con.commit()


def track_list(con):
    rows = con.execute(
        "SELECT c.name AS company, j.title, j.fingerprint, a.status, a.folder,"
        " a.notes, a.drafted_at, a.updated_at"
        " FROM Applications a JOIN Jobs j ON j.id = a.job_id"
        " JOIN Companies c ON c.id = j.company_id ORDER BY a.updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def log_search(con, provider, query, results_count, new_jobs_count):
    con.execute(
        "INSERT INTO SearchHistory (provider, query, results_count, new_jobs_count,"
        " run_at) VALUES (?,?,?,?,?)",
        (provider, query, results_count, new_jobs_count, now()))
    con.commit()


def stats(con, since_days):
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat(
        timespec="seconds")
    new_jobs = con.execute("SELECT COUNT(*) AS n FROM Jobs WHERE first_seen >= ?",
                           (since,)).fetchone()["n"]
    sh = con.execute(
        "SELECT COUNT(*) AS runs, COALESCE(SUM(results_count), 0) AS results"
        " FROM SearchHistory WHERE run_at >= ?", (since,)).fetchone()
    new_companies = [r["name"] for r in con.execute(
        "SELECT name FROM Companies WHERE discovered_at >= ? AND is_favorite = 0"
        " ORDER BY discovered_at DESC", (since,))]
    apps = {s: 0 for s in STATUSES}
    for r in con.execute("SELECT status, COUNT(*) AS n FROM Applications GROUP BY status"):
        apps[r["status"]] = r["n"]
    submitted = sum(apps[s] for s in ("Applied", "Interview", "Rejected", "Offer", "Accepted"))
    interviews = sum(apps[s] for s in ("Interview", "Offer", "Accepted"))
    rate = round(interviews / submitted, 3) if submitted else 0.0
    skills = Counter()
    for r in con.execute("SELECT stack FROM Jobs WHERE first_seen >= ?", (since,)):
        for skill in json.loads(r["stack"]):
            skills[skill] += 1
    return {
        "window_days": since_days,
        "new_jobs": new_jobs,
        "searches_run": sh["runs"],
        "results_total": sh["results"],
        "new_companies": new_companies,
        "applications": apps,
        "interview_rate": rate,
        "top_skills": skills.most_common(10),
    }


def list_companies(con, favorites_only=False):
    q = "SELECT * FROM Companies"
    if favorites_only:
        q += " WHERE is_favorite = 1"
    return [dict(r) for r in con.execute(q + " ORDER BY name")]


def main(argv=None):
    p = argparse.ArgumentParser(prog="db.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    fp = sub.add_parser("fingerprint")
    for f in ("--company", "--title", "--location", "--source"):
        fp.add_argument(f, required=(f != "--location"), default="")

    aj = sub.add_parser("add-job")
    aj.add_argument("--file", required=True)

    cj = sub.add_parser("cache-jd")
    cj.add_argument("--fingerprint", required=True)
    cj.add_argument("--file", required=True)

    gj = sub.add_parser("get-jd")
    gj.add_argument("--fingerprint", required=True)

    gjob = sub.add_parser("get-job")
    gjob.add_argument("--fingerprint", required=True)

    lj = sub.add_parser("list-jobs")
    lj.add_argument("--limit", type=int, default=200)

    kg = sub.add_parser("gaps")
    kg.add_argument("--min-score", type=int, default=45)
    kg.add_argument("--limit", type=int, default=25)

    rs = sub.add_parser("record-score")
    rs.add_argument("--fingerprint", required=True)
    rs.add_argument("--file", required=True)

    tr = sub.add_parser("track")
    tr.add_argument("--fingerprint")
    tr.add_argument("--status", choices=STATUSES)
    tr.add_argument("--folder")
    tr.add_argument("--notes")
    tr.add_argument("--list", action="store_true")

    ls = sub.add_parser("log-search")
    ls.add_argument("--provider", required=True)
    ls.add_argument("--query", required=True)
    ls.add_argument("--results", type=int, required=True)
    ls.add_argument("--new", type=int, required=True)

    uc = sub.add_parser("upsert-company")
    uc.add_argument("--name", required=True)
    uc.add_argument("--careers-url")
    uc.add_argument("--source")
    uc.add_argument("--funding-stage")
    uc.add_argument("--company-size")
    uc.add_argument("--industry")
    uc.add_argument("--remote-policy")
    uc.add_argument("--is-product", type=int, choices=(0, 1))
    uc.add_argument("--favorite", type=int, choices=(0, 1))

    lc = sub.add_parser("list-companies")
    lc.add_argument("--favorites-only", action="store_true")

    st = sub.add_parser("stats")
    st.add_argument("--since", type=int, default=7)

    args = p.parse_args(argv)
    con = connect()
    try:
        if args.cmd == "init":
            print(f"DB ready at {DB_PATH}")
        elif args.cmd == "fingerprint":
            print(make_fingerprint(args.company, args.title, args.location, args.source))
        elif args.cmd == "add-job":
            with open(args.file, encoding="utf-8") as f:
                print(json.dumps(add_job(con, json.load(f))))
        elif args.cmd == "cache-jd":
            with open(args.file, encoding="utf-8") as f:
                cache_jd(con, args.fingerprint, f.read())
            print("cached")
        elif args.cmd == "get-jd":
            jd = get_jd(con, args.fingerprint)
            if jd is None:
                sys.exit(3)
            print(jd)
        elif args.cmd == "get-job":
            job = get_job(con, args.fingerprint)
            if job is None:
                sys.exit(3)
            print(json.dumps(job, indent=2))
        elif args.cmd == "list-jobs":
            print(json.dumps(list_jobs(con, args.limit), indent=2))
        elif args.cmd == "gaps":
            print(json.dumps(keyword_gaps(con, args.min_score, args.limit), indent=2))
        elif args.cmd == "record-score":
            with open(args.file, encoding="utf-8") as f:
                record_score(con, args.fingerprint, json.load(f))
            print("scored")
        elif args.cmd == "track":
            if args.list:
                print(json.dumps(track_list(con), indent=2))
            else:
                if not args.fingerprint or not args.status:
                    p.error("track requires --fingerprint and --status (or --list)")
                track(con, args.fingerprint, args.status, args.folder, args.notes)
                print("tracked")
        elif args.cmd == "log-search":
            log_search(con, args.provider, args.query, args.results, args.new)
            print("logged")
        elif args.cmd == "upsert-company":
            cid, created = upsert_company(
                con, args.name, careers_url=args.careers_url, source=args.source,
                funding_stage=args.funding_stage, company_size=args.company_size,
                industry=args.industry, remote_policy=args.remote_policy,
                is_product_company=args.is_product, is_favorite=args.favorite)
            print(json.dumps({"company_id": cid, "created": created}))
        elif args.cmd == "list-companies":
            print(json.dumps(list_companies(con, args.favorites_only), indent=2))
        elif args.cmd == "stats":
            print(json.dumps(stats(con, args.since), indent=2))
    finally:
        con.close()


if __name__ == "__main__":
    main()
