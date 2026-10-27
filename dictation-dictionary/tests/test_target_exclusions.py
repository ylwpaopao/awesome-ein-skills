import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ddict
import transactions as tx
import vocabulary as vocab


def scoped_library():
    return vocab.merge_entries({"version": 1, "entries": []}, [
        {"term": "共享词"},
        {"term": "会议词", "excluded_targets": ["codex", "typeless"]},
        {"term": "停用词", "enabled": False}])


class TargetExclusionTests(unittest.TestCase):
    def test_target_exports_respect_persistent_exclusions(self):
        library = scoped_library()
        self.assertEqual(vocab.active_words(library), ["共享词", "会议词"])
        self.assertEqual(vocab.active_words(library, "plaud-cn"), ["共享词", "会议词"])
        self.assertEqual(vocab.active_words(library, "codex"), ["共享词"])
        self.assertEqual(vocab.active_words(library, "typeless"), ["共享词"])
        with self.assertRaises(ValueError):
            vocab.active_words(library, "plaud-ai")

    def test_legacy_entries_default_to_no_exclusions_and_updates_preserve_them(self):
        legacy = {"version": 1, "entries": [{"id": "legacy", "term": "共享词", "misheard_as": [],
                  "domains": [], "sources": [], "enabled": True}]}
        normalized = vocab.validate_library(legacy)
        self.assertEqual(normalized["entries"][0]["excluded_targets"], [])
        library = scoped_library()
        updated = vocab.merge_entries(library, [{"term": "会议词", "misheard_as": ["汇议词"]}])
        self.assertEqual(vocab.active_words(updated, "codex"), ["共享词"])
        cleared = vocab.merge_entries(updated, [{"term": "会议词", "excluded_targets": []}])
        self.assertEqual(vocab.active_words(cleared, "codex"), ["共享词", "会议词"])

    def test_invalid_exclusion_targets_fail_closed(self):
        for value in (["unknown"], "codex", None, ["codex", 1]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                vocab.merge_entries({"version": 1, "entries": []},
                                    [{"term": "会议词", "excluded_targets": value}])

    def test_cli_lists_exclusions_and_target_export_without_rewriting_library(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "vocabulary.json"
            path.write_bytes(vocab.library_bytes(scoped_library()))
            before = path.read_bytes()
            result = io.StringIO()
            with contextlib.redirect_stdout(result):
                self.assertEqual(ddict.main(["exclusions", "--library", str(path)]), 0)
            self.assertEqual(json.loads(result.getvalue()),
                             {"codex": ["会议词"], "typeless": ["会议词"], "plaud-cn": []})
            result = io.StringIO()
            with contextlib.redirect_stdout(result):
                self.assertEqual(ddict.main(["export", "--library", str(path), "--target", "codex"]), 0)
            self.assertEqual(json.loads(result.getvalue()), ["共享词"])
            self.assertEqual(path.read_bytes(), before)

    def test_library_driven_app_plans_filter_before_the_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lib = root / "vocabulary.json"
            lib.write_bytes(vocab.library_bytes(scoped_library()))
            config = root / "config.toml"
            config.write_text('[desktop]\ndictationDictionary = ["原有词"]\n')
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps({"target": "typeless", "words": ["原有词"], "complete": True,
                "evidence": {"kind": "count", "count": 1, "identity": "fixture",
                             "observed_at": "2026-10-27T00:00:00+00:00", "all_terms": True, "enabled": True}}))
            for command, options in [("codex-plan", ["--config", str(config)]),
                                     ("ui-plan", ["--inventory", str(inventory)])]:
                out = root / (command + ".json")
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(ddict.main([command, *options, "--library", str(lib), "--out", str(out)]), 0)
                plan = tx.load_plan(out)
                self.assertEqual(plan["after"]["words"], ["原有词", "共享词"])
            self.assertEqual(config.read_text(), '[desktop]\ndictationDictionary = ["原有词"]\n')


if __name__ == "__main__":
    unittest.main()
