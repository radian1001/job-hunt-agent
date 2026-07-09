import json
import os
import sqlite3
import tempfile
import unittest

# Point the module at a throwaway DB BEFORE importing it.
_tmpdir = tempfile.mkdtemp()
os.environ["JOBHUNT_DB"] = os.path.join(_tmpdir, "test.db")

import db  # noqa: E402


def sample_job(**overrides):
    job = {
        "company": "Acme Corp",
        "title": "Backend Engineer",
        "location": "Bengaluru, India",
        "remote_policy": "hybrid",
        "url": "https://acme.example/jobs/123",
        "source": "careers_page",
        "stack": ["Java", "Spring Boot", "PostgreSQL"],
        "yoe_min": 1, "yoe_max": 3,
        "seniority": "junior",
        "company_info": {"industry": "fintech", "is_product_company": 1},
    }
    job.update(overrides)
    return job


class TestFingerprint(unittest.TestCase):
    def test_stable_and_normalized(self):
        a = db.make_fingerprint("Acme Corp", "Backend Engineer", "Bengaluru, India", "careers_page")
        b = db.make_fingerprint("  acme  corp ", "BACKEND engineer", "bengaluru,   india", "Careers_Page")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 16)

    def test_differs_by_field(self):
        a = db.make_fingerprint("Acme", "Backend Engineer", "Bengaluru", "careers_page")
        b = db.make_fingerprint("Bcme", "Backend Engineer", "Bengaluru", "careers_page")
        c = db.make_fingerprint("Acme", "Backend Engineer", "Bengaluru", "remoteok")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.con = db.connect()

    def tearDown(self):
        self.con.close()

    def test_add_job_then_duplicate(self):
        r1 = db.add_job(self.con, sample_job())
        self.assertTrue(r1["new"])
        r2 = db.add_job(self.con, sample_job())
        self.assertFalse(r2["new"])
        self.assertEqual(r1["fingerprint"], r2["fingerprint"])
        count = self.con.execute("SELECT COUNT(*) FROM Jobs").fetchone()[0]
        self.assertEqual(count, 1)

    def test_jd_cache_roundtrip(self):
        r = db.add_job(self.con, sample_job(title="Platform Engineer"))
        self.assertIsNone(db.get_jd(self.con, r["fingerprint"]))
        db.cache_jd(self.con, r["fingerprint"], "# JD\nKafka required.")
        self.assertIn("Kafka", db.get_jd(self.con, r["fingerprint"]))

    def test_track_status_and_invalid(self):
        r = db.add_job(self.con, sample_job(title="SRE"))
        db.track(self.con, r["fingerprint"], "Drafted", folder="applications/acme-2026-07-09")
        db.track(self.con, r["fingerprint"], "Applied")
        rows = db.track_list(self.con)
        self.assertEqual(rows[0]["status"], "Applied")
        self.assertEqual(len(rows), 1)  # upsert, not a second row
        with self.assertRaises(sqlite3.IntegrityError):
            db.track(self.con, r["fingerprint"], "Ghosted")

    def test_record_score_and_stats(self):
        r = db.add_job(self.con, sample_job(title="Data Engineer"))
        db.record_score(self.con, r["fingerprint"], {
            "total": 78, "keyword_score": 24, "project_score": 12,
            "experience_score": 18, "location_score": 8, "seniority_score": 10,
            "company_score": 6,
            "matched_keywords": ["Java", "SQL"], "missing_keywords": ["Kafka"],
            "recommendation": "Strong Match", "explanation": "check Java, check SQL, miss Kafka",
        })
        db.log_search(self.con, "tinyfish_search", "Java Backend India", 12, 3)
        s = db.stats(self.con, since_days=7)
        self.assertGreaterEqual(s["new_jobs"], 1)
        self.assertEqual(s["searches_run"], 1)
        self.assertIn("interview_rate", s)
        self.assertTrue(any(skill == "Java" for skill, _ in s["top_skills"]))


if __name__ == "__main__":
    unittest.main()
