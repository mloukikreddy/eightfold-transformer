#!/usr/bin/env python3
"""Eightfold candidate data transformer.

Usage:
  python pipeline.py --sources sources.json [--config config.json] [--out out.json]

sources.json: list of source descriptors, e.g.
[
  {"type": "recruiter_csv", "path": "recruiter.csv"},
  {"type": "ats_json", "path": "ats.json"},
  {"type": "github_profile", "path": "alice_github.txt"},
  {"type": "linkedin_profile", "path": "alice_linkedin.txt"},
  {"type": "resume", "path": "alice_resume.txt"}
]

Records across all sources are assumed to be for ONE candidate per run
(grouping multiple candidates per run is a documented extension, see README).
"""
import argparse
import csv
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from normalizers import norm_recruiter_csv, norm_ats_json, norm_unstructured_text
from merge import merge_records
from project import apply_config

STRUCTURED_TYPES = {"recruiter_csv", "ats_json"}
UNSTRUCTURED_TYPES = {"github_profile", "linkedin_profile", "resume", "recruiter_notes", "portfolio"}

DEFAULT_CONFIG = {
    "fields": [
        {"path": "full_name", "type": "string", "required": True},
        {"path": "emails", "type": "string[]", "required": False},
        {"path": "phones", "type": "string[]", "required": False},
        {"path": "location", "type": "object", "required": False},
        {"path": "links", "type": "array", "required": False},
        {"path": "headline", "type": "string", "required": False},
        {"path": "years_experience", "type": "number", "required": False},
        {"path": "skills", "type": "array", "required": False},
        {"path": "experience", "type": "array", "required": False},
        {"path": "education", "type": "array", "required": False},
    ],
    "include_confidence": True,
    "on_missing": "null",
}


def load_source(desc):
    stype = desc["type"]
    path = desc["path"]
    source_id = desc.get("source_id", f"{stype}:{os.path.basename(path)}")

    if stype == "recruiter_csv":
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return {}, [], source_id, "structured"
        rec, prov = norm_recruiter_csv(rows[0], source_id)
        return rec, prov, source_id, "structured"

    if stype == "ats_json":
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        rec, prov = norm_ats_json(obj, source_id)
        return rec, prov, source_id, "structured"

    if stype in UNSTRUCTURED_TYPES:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        rec, prov = norm_unstructured_text(text, stype, source_id)
        return rec, prov, source_id, "unstructured"

    raise ValueError(f"unknown source type: {stype}")


def run_pipeline(source_descs, config=None):
    """Returns (output_dict, merge_conflicts, project_errors)."""
    config = config or DEFAULT_CONFIG
    partials = []
    for desc in source_descs:
        try:
            partials.append(load_source(desc))
        except FileNotFoundError as e:
            print(f"warning: source unreadable, skipping: {e}", file=sys.stderr)
        except (json.JSONDecodeError, csv.Error) as e:
            print(f"warning: source malformed, skipping {desc.get('path')}: {e}", file=sys.stderr)

    merged, _prov, conflicts = merge_records(partials)
    output, errors = apply_config(merged, config)
    return output, conflicts, errors


def main():
    ap = argparse.ArgumentParser(description="Eightfold candidate data transformer")
    ap.add_argument("--sources", required=True, help="JSON file listing source descriptors")
    ap.add_argument("--config", help="JSON file with output config (default: built-in default schema)")
    ap.add_argument("--out", help="output JSON path (default: stdout)")
    args = ap.parse_args()

    with open(args.sources, encoding="utf-8") as f:
        source_descs = json.load(f)

    config = DEFAULT_CONFIG
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)

    output, conflicts, errors = run_pipeline(source_descs, config)

    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    result = json.dumps(output, indent=2, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(result)

    if conflicts:
        print(f"note: {len(conflicts)} field conflict(s) resolved by source weight, see provenance/conflicts", file=sys.stderr)


if __name__ == "__main__":
    main()
