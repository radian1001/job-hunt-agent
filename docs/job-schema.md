# Canonical Job JSON

Every provider's extraction output is normalized to this shape before storage.
`python scripts/db.py add-job --file <path>` consumes exactly this format.
Write these files to `state/tmp/job-<n>.json` during a scan.

## Required fields
| Field | Type | Notes |
|-------|------|-------|
| `company` | string | Company display name, e.g. "Razorpay" |
| `title` | string | Role title as posted |
| `source` | string | Provider id from config/providers.json |

## Optional fields
| Field | Type | Notes |
|-------|------|-------|
| `location` | string | "Bengaluru, India" / "Remote (India)" — used in the fingerprint; use "" if unknown |
| `remote_policy` | string | "remote" / "hybrid" / "onsite" if stated |
| `url` | string | Absolute posting URL |
| `stack` | array of strings | Technologies named in the posting, e.g. ["Java", "Spring Boot"] |
| `yoe_min` / `yoe_max` | number | Required years of experience range if stated |
| `seniority` | string | "intern" / "junior" / "mid" / "senior" / "staff+" |
| `company_info` | object | Company intelligence, merged into the Companies table |

## `company_info` fields (all optional, store only what the page states)
| Field | Type |
|-------|------|
| `careers_url` | string |
| `funding_stage` | string (e.g. "Seed", "Series B", "Public") |
| `company_size` | string (e.g. "11-50", "1000+") |
| `industry` | string |
| `remote_policy` | string |
| `is_product_company` | 0 or 1 |
| `is_favorite` | 0 or 1 |

## Identity
Dedup fingerprint = sha256 of normalized `company|title|location|source`, first 16
hex chars — computed by db.py, never by hand. Same role reposted at the same
company/location/source is a duplicate; the same role found via two providers is
intentionally two rows (different `source`).

## Example
{
  "company": "Razorpay",
  "title": "Software Engineer - Backend",
  "location": "Bengaluru, India",
  "remote_policy": "hybrid",
  "url": "https://razorpay.com/jobs/123",
  "source": "careers_page",
  "stack": ["Java", "Spring Boot", "MySQL", "Kafka"],
  "yoe_min": 1,
  "yoe_max": 3,
  "seniority": "junior",
  "company_info": {"industry": "fintech", "is_product_company": 1, "is_favorite": 1}
}
