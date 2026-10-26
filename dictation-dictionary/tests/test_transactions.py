import json
import contextlib
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import transactions as tx
except ModuleNotFoundError:
    tx = None


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(tx, "transaction module is not implemented")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.config = self.root / "config.toml"
        self.old = b'model = "before"\n[desktop]\ndictationDictionary = ["old"]\nflag = true\n'
        self.config.write_bytes(self.old)
        self.config.chmod(0o600)

    def test_no_approval_or_modified_plan_cannot_write(self):
        plan = tx.plan_codex(self.config, ["new"])
        approval = tx.plan_id(plan)
        with self.assertRaises(ValueError):
            tx.apply_file_plan(plan, "", self.state)
        plan["after"]["words"].append("unapproved")
        with self.assertRaises(ValueError):
            tx.apply_file_plan(plan, approval, self.state)
        self.assertEqual(self.config.read_bytes(), self.old)

    def test_changed_source_rejects_stale_approval(self):
        plan = tx.plan_codex(self.config, ["new"])
        changed = self.old.replace(b'"before"', b'"changed"')
        self.config.write_bytes(changed)
        with self.assertRaises(ValueError):
            tx.apply_file_plan(plan, tx.plan_id(plan), self.state)
        self.assertEqual(self.config.read_bytes(), changed)

    def test_backup_failure_leaves_source_untouched(self):
        plan = tx.plan_codex(self.config, ["new"])
        with patch.object(tx, "backup_bytes", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                tx.apply_file_plan(plan, tx.plan_id(plan), self.state)
        self.assertEqual(self.config.read_bytes(), self.old)

    def test_backup_precedes_write_and_repeat_does_not_add_duplicates(self):
        plan = tx.plan_codex(self.config, ["new"])
        receipt = tx.apply_file_plan(plan, tx.plan_id(plan), self.state)
        self.assertEqual(Path(receipt["backup"]).read_bytes(), self.old)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(Path(receipt["backup"]).stat().st_mode), 0o600)
        self.assertEqual(self.config.read_bytes(), self.old.replace(b'["old"]', b'["old", "new"]'))
        self.assertEqual(tx.apply_file_plan(plan, tx.plan_id(plan), self.state)["status"], "already_applied")
        self.assertEqual(len(list((self.state / "backups").glob("*.toml"))), 1)

    def test_no_change_does_not_rewrite_or_backup(self):
        plan = tx.plan_codex(self.config, ["old"])
        stamp = self.config.stat().st_mtime_ns
        receipt = tx.apply_file_plan(plan, tx.plan_id(plan), self.state)
        self.assertEqual(receipt["status"], "unchanged")
        self.assertEqual(self.config.stat().st_mtime_ns, stamp)
        self.assertFalse((self.state / "backups").exists())

    def test_restore_only_dictionary_keeps_settings_changed_since_backup(self):
        plan = tx.plan_codex(self.config, ["new"])
        receipt = tx.apply_file_plan(plan, tx.plan_id(plan), self.state)
        current = self.config.read_bytes().replace(b'"before"', b'"new preference"')
        self.config.write_bytes(current)
        restore = tx.plan_restore_codex(self.config, Path(receipt["backup"]))
        tx.apply_file_plan(restore, tx.plan_id(restore), self.state)
        self.assertEqual(self.config.read_bytes(), self.old.replace(b'"before"', b'"new preference"'))

    def test_initial_library_creation_is_approved_and_absence_is_backed_up(self):
        path = self.root / "store" / "vocabulary.json"
        library = {"version": 1, "entries": []}
        plan = tx.plan_library(path, library)
        self.assertFalse(path.exists())
        with self.assertRaises(ValueError):
            tx.apply_file_plan(plan, "", self.state)
        receipt = tx.apply_file_plan(plan, tx.plan_id(plan), self.state)
        self.assertEqual(json.loads(path.read_text()), library)
        self.assertEqual(json.loads(Path(receipt["backup"]).read_text()), {"existed": False})

    def test_symbolic_link_target_is_rejected(self):
        link = self.root / "alias.toml"
        link.symlink_to(self.config)
        with self.assertRaises(ValueError):
            tx.plan_codex(link, ["new"])
        self.assertEqual(self.config.read_bytes(), self.old)

    def test_cli_plan_is_read_only_then_apply_requires_approved_id(self):
        import ddict
        path = self.root / "words.json"
        path.write_text('["new"]')
        preview = self.root / "plans" / "change.json"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                result = ddict.main(["codex-plan", "--config", str(self.config),
                                     "--words", str(path), "--out", str(preview)])
            except SystemExit:
                result = -1
        self.assertEqual(result, 0, "codex-plan command must exist")
        self.assertEqual(self.config.read_bytes(), self.old)
        ident = json.loads(preview.read_text())["id"]
        self.assertNotIn('model =', preview.read_text())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ddict.main(["apply", "--plan", str(preview), "--state", str(self.state)]), 1)
        self.assertEqual(self.config.read_bytes(), self.old)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ddict.main(["apply", "--plan", str(preview), "--approve", ident,
                                         "--state", str(self.state)]), 0)
        self.assertEqual(self.config.read_bytes(), self.old.replace(b'["old"]', b'["old", "new"]'))

    def test_cli_candidate_plan_does_not_create_main_library(self):
        import ddict
        path = self.root / "vocabulary.json"
        candidates = self.root / "candidates.json"
        candidates.write_text('[{"term": "项目甲"}]')
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                result = ddict.main(["library-plan", "--library", str(path), "--candidates", str(candidates),
                                     "--out", str(self.root / "plans" / "library.json")])
            except SystemExit:
                result = -1
        self.assertEqual(result, 0, "library-plan command must exist")
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
