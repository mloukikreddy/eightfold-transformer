"""Merge partial canonical records from multiple sources into one candidate record.

Strategy:
- Structured sources trusted more than unstructured (base weight).
- List fields (emails, phones, skills, links, experience, education): union/de-dupe.
- Scalar fields (full_name, headline, years_experience): highest-weight source wins;
  conflicting values recorded in provenance, not silently dropped.
- overall_confidence: weighted avg of per-field confidence, scaled by source count agreement.
"""

SOURCE_WEIGHTS = {
    "structured": 1.0,
    "unstructured": 0.55,
}

LIST_FIELDS = {"emails", "phones", "skills", "links", "experience", "education"}
SCALAR_FIELDS = {"full_name", "headline", "years_experience", "location"}


def merge_records(partials):
    """partials: list of (record_dict, provenance_list, source_id, source_class)
    source_class: 'structured' | 'unstructured'
    Returns (merged_record, full_provenance, conflicts)
    """
    merged = {}
    provenance = []
    conflicts = []
    scalar_candidates = {}  # field -> list of (value, weight, source)

    for rec, prov, source_id, source_class in partials:
        weight = SOURCE_WEIGHTS.get(source_class, 0.5)
        provenance.extend(prov)
        for field, value in rec.items():
            if field in LIST_FIELDS:
                merged.setdefault(field, [])
                merged[field] = _merge_list(merged[field], value, field)
            elif field in SCALAR_FIELDS:
                scalar_candidates.setdefault(field, []).append((value, weight, source_id))

    for field, candidates in scalar_candidates.items():
        candidates.sort(key=lambda c: c[1], reverse=True)
        best_value, best_weight, best_source = candidates[0]
        merged[field] = best_value
        distinct_vals = {str(c[0]) for c in candidates}
        if len(distinct_vals) > 1:
            conflicts.append({
                "field": field,
                "chosen": best_value,
                "chosen_source": best_source,
                "alternatives": [{"value": c[0], "source": c[2]} for c in candidates[1:]],
            })

    merged["provenance"] = provenance
    merged["overall_confidence"] = _compute_confidence(partials, conflicts, merged)
    return merged, provenance, conflicts


def _merge_list(existing, new_items, field):
    if field == "skills":
        by_name = {s["name"].lower(): s for s in existing}
        for s in new_items:
            key = s["name"].lower()
            if key in by_name:
                cur = by_name[key]
                cur["confidence"] = max(cur["confidence"], s["confidence"])
                cur["sources"] = sorted(set(cur["sources"] + s["sources"]))
            else:
                by_name[key] = dict(s)
        return list(by_name.values())
    if field in ("emails", "phones"):
        seen = list(existing)
        for v in new_items:
            if v not in seen:
                seen.append(v)
        return seen
    # links / experience / education: de-dupe by stringified content
    seen = list(existing)
    seen_keys = {str(x) for x in seen}
    for v in new_items:
        if str(v) not in seen_keys:
            seen.append(v)
            seen_keys.add(str(v))
    return seen


def _compute_confidence(partials, conflicts, merged):
    if not partials:
        return 0.0
    source_classes = [p[3] for p in partials]
    weights = [SOURCE_WEIGHTS.get(c, 0.5) for c in source_classes]
    base = sum(weights) / len(weights)
    # more independent sources agreeing -> small boost; conflicts -> penalty
    n_sources = len(set(p[2] for p in partials))
    agreement_bonus = min(0.15, 0.05 * (n_sources - 1))
    conflict_penalty = min(0.3, 0.1 * len(conflicts))
    score = base + agreement_bonus - conflict_penalty
    return round(max(0.0, min(1.0, score)), 3)
