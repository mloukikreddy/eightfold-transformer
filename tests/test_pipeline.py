import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from normalizers import norm_recruiter_csv, norm_ats_json, norm_unstructured_text, normalize_phone, parse_location
from merge import merge_records
from project import apply_config


class TestNormalizers(unittest.TestCase):
    def test_recruiter_csv(self):
        row = {"name": "Bob Lee", "email": "Bob@Example.com", "phone": "650-555-0100", "current_title": "PM"}
        rec, prov = norm_recruiter_csv(row, "src1")
        self.assertEqual(rec["full_name"], "Bob Lee")
        self.assertEqual(rec["emails"], ["bob@example.com"])
        self.assertEqual(rec["phones"], ["+16505550100"])
        self.assertTrue(any(p["field"] == "full_name" for p in prov))

    def test_ats_json_field_mismatch(self):
        obj = {"fullName": "Bob Lee", "email": "bob@x.com", "location": "Austin, USA"}
        rec, prov = norm_ats_json(obj, "src2")
        self.assertEqual(rec["full_name"], "Bob Lee")
        self.assertEqual(rec["location"]["city"], "Austin")

    def test_unstructured_extraction(self):
        text = "Name: Carl Yu\nSkills: Rust, C++\n5 years experience"
        rec, prov = norm_unstructured_text(text, "resume", "src3")
        self.assertEqual(rec["full_name"], "Carl Yu")
        self.assertEqual(rec["years_experience"], 5.0)
        self.assertEqual(len(rec["skills"]), 2)

    def test_unstructured_no_match_no_crash(self):
        text = "garbage data with no recognizable fields at all"
        rec, prov = norm_unstructured_text(text, "resume", "src4")
        self.assertEqual(rec, {})
        self.assertEqual(prov, [])

    def test_normalize_phone_variants(self):
        self.assertEqual(normalize_phone("415-555-0192"), "+14155550192")
        self.assertEqual(normalize_phone("+44 20 7946 0958"), "+442079460958")

    def test_parse_location_variants(self):
        self.assertEqual(parse_location("Austin"), {"city": "Austin", "region": None, "country": None})
        self.assertEqual(parse_location("SF, CA, USA")["region"], "CA")


class TestMerge(unittest.TestCase):
    def test_merge_union_and_conflict(self):
        p1 = ({"full_name": "Dana A", "emails": ["d@x.com"]}, [], "s1", "structured")
        p2 = ({"full_name": "Dana B", "emails": ["d2@x.com"]}, [], "s2", "unstructured")
        merged, prov, conflicts = merge_records([p1, p2])
        self.assertEqual(merged["full_name"], "Dana A")  # structured wins
        self.assertIn("d@x.com", merged["emails"])
        self.assertIn("d2@x.com", merged["emails"])
        self.assertEqual(len(conflicts), 1)

    def test_skills_dedupe_confidence_max(self):
        p1 = ({"skills": [{"name": "python", "confidence": 0.5, "sources": ["a"]}]}, [], "a", "unstructured")
        p2 = ({"skills": [{"name": "Python", "confidence": 0.9, "sources": ["b"]}]}, [], "b", "structured")
        merged, _, _ = merge_records([p1, p2])
        self.assertEqual(len(merged["skills"]), 1)
        self.assertEqual(merged["skills"][0]["confidence"], 0.9)

    def test_empty_partials(self):
        merged, prov, conflicts = merge_records([])
        self.assertEqual(merged["overall_confidence"], 0.0)


class TestProject(unittest.TestCase):
    def test_select_rename_normalize(self):
        record = {"full_name": "  Eve  ", "emails": ["eve@x.com"], "overall_confidence": 0.7, "provenance": []}
        config = {
            "fields": [
                {"path": "name", "from": "full_name", "normalize": "strip"},
                {"path": "primary_email", "from": "emails[0]"},
            ],
            "include_confidence": True,
            "on_missing": "null",
        }
        out, errors = apply_config(record, config)
        self.assertEqual(out["name"], "Eve")
        self.assertEqual(out["primary_email"], "eve@x.com")
        self.assertEqual(errors, [])

    def test_required_missing_errors(self):
        record = {"overall_confidence": 0.1, "provenance": []}
        config = {
            "fields": [{"path": "full_name", "required": True}],
            "on_missing": "error",
        }
        out, errors = apply_config(record, config)
        self.assertEqual(len(errors), 1)

    def test_on_missing_omit(self):
        record = {"overall_confidence": 0.1, "provenance": []}
        config = {"fields": [{"path": "headline"}], "on_missing": "omit", "include_confidence": False}
        out, errors = apply_config(record, config)
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
