"""Normalizers: each source type -> partial canonical record + provenance."""
import re
import uuid


def _split_name(name):
    parts = name.strip().split()
    return name.strip()


def norm_recruiter_csv(row, source_id="recruiter_csv"):
    """row: dict with keys like name,email,phone,current_title (case-insensitive, fuzzy)."""
    rec = {}
    prov = []

    def get(*keys):
        for k in row:
            if k.strip().lower().replace(" ", "_") in keys:
                return row[k]
        return None

    name = get("name", "full_name")
    email = get("email")
    phone = get("phone", "phone_number")
    title = get("current_title", "title", "current_position")

    if name:
        rec["full_name"] = name.strip()
        prov.append({"field": "full_name", "source": source_id, "method": "direct"})
    if email:
        rec["emails"] = [email.strip().lower()]
        prov.append({"field": "emails", "source": source_id, "method": "direct"})
    if phone:
        rec["phones"] = [normalize_phone(phone)]
        prov.append({"field": "phones", "source": source_id, "method": "normalized:E.164"})
    if title:
        rec["headline"] = title.strip()
        prov.append({"field": "headline", "source": source_id, "method": "direct"})

    return rec, prov


def norm_ats_json(obj, source_id="ats_json"):
    """obj: dict, semi-structured, field names may not match canonical schema."""
    rec = {}
    prov = []
    fmap = {
        "name": "full_name", "fullName": "full_name", "candidate_name": "full_name",
        "email": "emails", "emails": "emails", "contact_email": "emails",
        "phone": "phones", "phones": "phones", "mobile": "phones",
        "title": "headline", "current_role": "headline", "position": "headline",
        "city": "_city", "location": "_location_raw", "country": "_country",
        "years": "years_experience", "experience_years": "years_experience",
        "skills": "_skills_raw",
    }
    city = country = None
    for k, v in obj.items():
        target = fmap.get(k)
        if target is None or v in (None, "", []):
            continue
        if target == "emails":
            vals = v if isinstance(v, list) else [v]
            rec["emails"] = [e.strip().lower() for e in vals]
            prov.append({"field": "emails", "source": source_id, "method": "direct"})
        elif target == "phones":
            vals = v if isinstance(v, list) else [v]
            rec["phones"] = [normalize_phone(p) for p in vals]
            prov.append({"field": "phones", "source": source_id, "method": "normalized:E.164"})
        elif target == "full_name":
            rec["full_name"] = v.strip()
            prov.append({"field": "full_name", "source": source_id, "method": "direct"})
        elif target == "headline":
            rec["headline"] = v.strip()
            prov.append({"field": "headline", "source": source_id, "method": "direct"})
        elif target == "years_experience":
            try:
                rec["years_experience"] = float(v)
                prov.append({"field": "years_experience", "source": source_id, "method": "direct"})
            except (ValueError, TypeError):
                pass
        elif target == "_city":
            city = v
        elif target == "_country":
            country = v
        elif target == "_location_raw":
            rec["location"] = parse_location(v)
            prov.append({"field": "location", "source": source_id, "method": "parsed"})
        elif target == "_skills_raw":
            skills = v if isinstance(v, list) else [s.strip() for s in str(v).split(",")]
            rec["skills"] = [{"name": s, "confidence": 0.8, "sources": [source_id]} for s in skills if s]
            prov.append({"field": "skills", "source": source_id, "method": "direct"})
    if city and "location" not in rec:
        rec["location"] = {"city": city, "region": None, "country": country}
        prov.append({"field": "location", "source": source_id, "method": "direct"})
    return rec, prov


def norm_unstructured_text(text, kind, source_id):
    """kind: 'github_profile' | 'linkedin_profile' | 'resume' | 'recruiter_notes'
    text: raw scraped/pasted text blob.
    Heuristic regex extraction -> lower confidence than structured sources."""
    rec = {}
    prov = []

    email_m = re.search(r"[\w\.+-]+@[\w\.-]+\.\w+", text)
    if email_m:
        rec["emails"] = [email_m.group(0).lower()]
        prov.append({"field": "emails", "source": source_id, "method": "regex_extracted"})

    phone_m = re.search(r"(\+?\d[\d\-\.\(\) ]{7,}\d)", text)
    if phone_m:
        rec["phones"] = [normalize_phone(phone_m.group(0))]
        prov.append({"field": "phones", "source": source_id, "method": "regex_extracted+normalized"})

    name_m = re.search(r"(?:Name|Profile)\s*[:\-]\s*(.+)", text)
    if name_m:
        rec["full_name"] = name_m.group(1).strip()
        prov.append({"field": "full_name", "source": source_id, "method": "regex_extracted"})

    skills_m = re.search(r"Skills?\s*[:\-]\s*(.+)", text)
    if skills_m:
        skills = [s.strip() for s in re.split(r"[,;]", skills_m.group(1)) if s.strip()]
        rec["skills"] = [{"name": s, "confidence": 0.5, "sources": [source_id]} for s in skills]
        prov.append({"field": "skills", "source": source_id, "method": "regex_extracted", "confidence_note": "unstructured:lower"})

    years_m = re.search(r"(\d+)\+?\s*years? (?:of )?experience", text, re.I)
    if years_m:
        rec["years_experience"] = float(years_m.group(1))
        prov.append({"field": "years_experience", "source": source_id, "method": "regex_extracted"})

    if kind in ("github_profile", "linkedin_profile", "portfolio"):
        rec.setdefault("links", []).append({"type": kind, "url": source_id})
        prov.append({"field": "links", "source": source_id, "method": "direct"})

    headline_m = re.search(r"(?:Headline|Title|Role)\s*[:\-]\s*(.+)", text)
    if headline_m:
        rec["headline"] = headline_m.group(1).strip()
        prov.append({"field": "headline", "source": source_id, "method": "regex_extracted"})

    return rec, prov


def normalize_phone(raw):
    """Best-effort E.164. If country code absent and looks like 10-digit US, assume +1.
    Cannot fully validate without a real phone lib offline; flags ambiguous results."""
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("+"):
        return digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits  # best-effort, flagged via provenance method name upstream


def parse_location(raw):
    """'City, Country' or 'City, Region, Country' -> dict. Best-effort."""
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) == 1:
        return {"city": parts[0], "region": None, "country": None}
    if len(parts) == 2:
        return {"city": parts[0], "region": None, "country": parts[1]}
    return {"city": parts[0], "region": parts[1], "country": parts[-1]}
