# Eightfold Candidate Data Transformer

Author: Mekala Loukik Reddy · mloukikreddy@gmail.com · github.com/mloukikreddy

Merges candidate data from multiple structured and unstructured sources into one
canonical schema, with per-field provenance and confidence, and a runtime config
that controls what the output looks like.

## Quick start

```bash
cd eightfold
python3 src/pipeline.py --sources sample_data/sources.json --out output/result.json
cat output/result.json
```

With a custom output config (subset/rename/normalize fields):

```bash
python3 src/pipeline.py \
  --sources sample_data/sources.json \
  --config sample_data/config_min_phones.json \
  --out output/result_custom.json
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

## Inputs

`--sources` points to a JSON file listing source descriptors:

```json
[
  {"type": "recruiter_csv", "path": "recruiter.csv"},
  {"type": "ats_json", "path": "ats.json"},
  {"type": "github_profile", "path": "alice_github.txt"},
  {"type": "linkedin_profile", "path": "alice_linkedin.txt"}
]
```

Supported `type`s:
- `recruiter_csv` — structured. Fuzzy column matching (name/full_name, email, phone,
  current_title/title).
- `ats_json` — structured. Field-name map (`fullName`/`name`/`candidate_name` -> `full_name`,
  etc.), tolerant of ATS-specific naming.
- `github_profile`, `linkedin_profile`, `resume`, `recruiter_notes`, `portfolio` — unstructured
  text blobs. Heuristic regex extraction (email, phone, "Name:"/"Skills:"/"N years experience").
  **This build reads local text files standing in for scraped/pasted profile content**; a real
  deployment would plug in an HTTP fetcher + HTML-to-text step ahead of `norm_unstructured_text`
  (see "Notes / scope cuts" below).

All sources in one `--sources` file are treated as **one candidate** per run. Multi-candidate
batch runs are not implemented — see scope cuts.

## Output

Default config (`pipeline.DEFAULT_CONFIG`) emits the full canonical schema (see
`src/schema.py`). A custom `--config` file controls:

- **field selection** — only listed `fields` appear in output
- **rename/remap** — `"path"` is the output key, `"from"` is the canonical-record path to
  read (dot + `[index]` syntax, e.g. `skills[0].name`)
- **per-field normalize** — `lower`, `upper`, `strip` built in (phones are already E.164
  upstream; `normalize: "E.164"` in config is a documented no-op hook for re-normalizing
  a remapped field)
- **on_missing** — `"null"` (default, keep key with null), `"omit"` (drop key), or `"error"`
  (fail the run, required fields only block on error)
- **include_confidence** — toggle `overall_confidence` + `provenance` in output

Example config: `sample_data/config_min_phones.json`.

## Design

Pipeline: **detect source type → normalize → merge → project (apply config) → validate**.

- `src/normalizers.py` — one function per source type, each returns
  `(partial_record, provenance_list)`. Structured sources are field-mapped; unstructured
  sources are regex-extracted with a `confidence_note` flag since extraction is lossier.
- `src/merge.py` — combines partials. List fields (`emails`, `phones`, `skills`, `links`,
  `experience`, `education`) are unioned/de-duped (skills de-dupe by lowercased name, keeping
  max confidence and merging `sources`). Scalar fields (`full_name`, `headline`,
  `years_experience`, `location`) pick the highest-weight source; conflicting values are
  **not silently dropped** — recorded under `conflicts` and surfaced as a CLI stderr note.
  Structured sources are weighted 1.0, unstructured 0.55. `overall_confidence` blends source
  weight, source-count agreement, and a conflict penalty.
- `src/project.py` — applies the runtime config: path lookup, rename, normalize, missing
  handling.
- `src/pipeline.py` — orchestrates + CLI. Bad/missing source files are skipped with a stderr
  warning rather than crashing the run (tested in `sample_data/sources_with_garbage.json`).

## Deterministic & robust

- No randomness, no external network/model calls — same inputs always produce the same
  output JSON (field/list ordering, confidence scores).
- Unreadable, malformed, or missing source files are skipped with a warning, not a crash.
  Unparseable text fields just don't populate (no exceptions thrown from regex misses).
- Garbled/garbage unstructured text degrades gracefully to an empty partial record rather
  than emitting garbage values (see `test_unstructured_no_match_no_crash`).

## Notes / scope cuts (documented, not hidden)

- **No live HTTP fetching.** `github_profile`/`linkedin_profile`/etc. sources are read from
  local text files as a stand-in for "already scraped/pasted" content. Wiring in a real
  fetcher + HTML stripper is a small addition at `load_source()` in `pipeline.py` and was cut
  for time, not because it's hard.
  This is a structurally clean place to add it, but real LinkedIn/GitHub scraping has
  ToS/auth complications that are out of scope for this exercise.
- **Phone normalization is best-effort.** Without a real phone-number library (offline
  environment), `normalize_phone()` assumes a bare 10-digit number is US/+1. International
  numbers without a `+` prefix may normalize incorrectly — flagged via provenance method name,
  not silently trusted.
- **One candidate per pipeline run.** Batch/multi-candidate mode (group source rows by an ID
  column) is a natural extension but wasn't built — `recruiter_csv` normalizer reads only the
  first CSV row.
- **Confidence scoring is a simple heuristic** (source-type weight + agreement bonus - conflict
  penalty), not a learned model. Documented in `merge.py`, easy to swap out.

## Tests

12 unit tests in `tests/test_pipeline.py` cover: fuzzy structured field mapping, unstructured
regex extraction (incl. no-match case), phone/location parsing, merge union + scalar conflict
resolution, skills de-dupe, empty-input edge case, and config projection (rename, normalize,
required-missing error, omit-on-missing).
