"""Default canonical schema for Eightfold candidate transformer."""

DEFAULT_SCHEMA = {
    "candidate_id": "string",
    "full_name": "string",
    "emails": "string[]",
    "phones": "string[]",
    "location": "{ city, region, country }",
    "links": "[{linkedin, github, portfolio, other}]",
    "headline": "string | null",
    "years_experience": "number | null",
    "skills": "[{name, confidence, sources[]}]",
    "experience": "[{company, title, start, end, source}]",
    "education": "[{institution, degree, field, end_year}]",
    "provenance": "[{field, source, method}]",
    "overall_confidence": "number",
}
