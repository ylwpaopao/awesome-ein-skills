import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import vocabulary
except ModuleNotFoundError:
    vocabulary = None


def entry(term, **changes):
    value = {"id": "id-" + term, "term": term, "misheard_as": [],
             "domains": [], "sources": [], "enabled": True}
    value.update(changes)
    return value


class VocabularyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(vocabulary, "vocabulary module is not implemented")

    def test_exports_only_enabled_correct_spellings_and_preserves_phrases(self):
        lib = {"version": 1, "entries": [
            entry("项目甲", misheard_as=["项目假"], domains=["研究"],
                  sources=[{"url": "https://example.com/notes", "locator": "00:03"}]),
            entry("Claude Code"), entry("旧项目", enabled=False)]}
        self.assertEqual(vocabulary.active_words(lib), ["项目甲", "Claude Code"])

    def test_does_not_merge_homophones_or_case_variants(self):
        lib = vocabulary.merge_entries({"version": 1, "entries": []},
                                       [{"term": t} for t in ["王蕾", "王磊", "CLI", "cli"]])
        self.assertEqual(vocabulary.active_words(lib), ["王蕾", "王磊", "CLI", "cli"])

    def test_merges_sources_without_mutating_inputs_and_is_idempotent(self):
        old = {"version": 1, "entries": [entry("项目甲", sources=[{"url": "https://example.com/a"}])]}
        saved = copy.deepcopy(old)
        candidates = [{"term": "项目甲", "misheard_as": ["项目假"],
                       "sources": [{"url": "https://example.com/a"}, {"url": "https://example.com/b"}]}]
        result = vocabulary.merge_entries(old, candidates)
        self.assertEqual(old, saved)
        self.assertEqual(result["entries"][0]["id"], "id-项目甲")
        self.assertEqual(result["entries"][0]["sources"],
                         [{"url": "https://example.com/a"}, {"url": "https://example.com/b"}])
        self.assertEqual(result["entries"][0]["misheard_as"], ["项目假"])
        self.assertEqual(vocabulary.merge_entries(result, candidates), result)

    def test_generated_ids_are_stable_between_independent_devices(self):
        a = vocabulary.merge_entries({"version": 1, "entries": []}, [{"term": "项目甲"}])
        b = vocabulary.merge_entries({"version": 1, "entries": []}, [{"term": "项目甲"}])
        self.assertEqual(a["entries"][0]["id"], b["entries"][0]["id"])

    def test_diff_exposes_actual_additions_and_removals(self):
        result = vocabulary.diff_words(["已有词", "旧词"], ["已有词", "新词"])
        self.assertEqual(result, {"added": ["新词"], "removed": ["旧词"], "unchanged": ["已有词"]})

    def test_rejects_malformed_library_instead_of_saving_arbitrary_material(self):
        bad = [
            {"version": True, "entries": []},
            {"version": 1, "entries": [entry("项目甲"), entry("项目甲")]},
            {"version": 1, "entries": [entry("a", id="same"), entry("b", id="same")]},
            {"version": 1, "entries": [entry("a\nb")]},
            {"version": 1, "entries": [entry(" a ")]},
            {"version": 1, "entries": [entry("a", enabled="yes")]},
            {"version": 1, "entries": [entry("a", transcript="meeting body")]},
            {"version": 1, "entries": [entry("a", sources=[{"url": "https://example.com", "body": "meeting body"}])]},
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                vocabulary.validate_library(value)

    def test_read_only_cli_export_leaves_library_untouched(self):
        import ddict
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "vocabulary.json"
            data = json.dumps({"version": 1, "entries": [entry("项目甲")]}, ensure_ascii=False).encode()
            path.write_bytes(data)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = ddict.main(["export", "--library", str(path), "--format", "json"])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue()), ["项目甲"])
            self.assertEqual(path.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
