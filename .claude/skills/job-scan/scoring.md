# Scoring Rubric (0-100)

Score each NEW job against config/resume.md. Components:

| Component | Max | How to judge |
|-----------|-----|--------------|
| keyword_score | 30 | Fraction of the JD's named technologies/skills that appear in the resume (Skills + Experience + Projects sections). |
| experience_score | 20 | Resume YOE vs the role's yoe_min-yoe_max: full points in range, taper by ~5 points per year outside. |
| project_score | 15 | Do the resume's projects demonstrate the JD's core domain (e.g. built a REST API in Spring for a Spring Boot role)? |
| seniority_score | 15 | Title level vs resume level: exact match full, one level off half, two+ levels zero. |
| location_score | 10 | Full: remote-ok or same city. Half: same country, relocation plausible. Zero: incompatible. |
| company_score | 10 | Product company with real engineering brand high; staffing/consultancy low. Use company_info when present. |

semantic_score: leave null. The ResumeScores table reserves a REAL column so an
embedding-based similarity provider can be added later without a schema change.

## Explanation (required for every score)
List the decisive matched and missing keywords with check/cross marks, then a
recommendation band:

    matched: Java, Spring Boot, SQL
    missing: Kafka, AWS
    ...rendered in digests as:
    [+] Java  [+] Spring Boot  [+] SQL
    [-] Kafka  [-] AWS

Recommendation bands: total >= 75 "Strong Match", 60-74 "Good Match",
45-59 "Possible Match", < 45 "Skip".

## Storage
Write the score JSON to state/tmp/score-<fingerprint>.json with fields:
total, keyword_score, project_score, experience_score, location_score,
seniority_score, company_score, matched_keywords (array), missing_keywords
(array), recommendation, explanation (the rendered [+]/[-] block as one string).
Then: python scripts/db.py record-score --fingerprint <fp> --file <that file>
