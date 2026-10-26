import contextlib
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import transactions as tx
try:
    import ui_sync as ui
except ModuleNotFoundError:
    ui = None


def inventory(values, target="plaud-cn", **evidence):
    proof = {"kind": "count", "count": len(values), "identity": "fixture-account",
             "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
             "all_terms": True, "enabled": True}
    proof.update(evidence)
    return {"target": target, "words": values, "complete": True, "evidence": proof}


class UISyncTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(ui, "UI approval adapter is not implemented")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_incomplete_filtered_duplicate_or_background_snapshot_is_rejected(self):
        bad = [dict(inventory(["old"]), complete=False),
               inventory(["old"], count=4), inventory(["old"], all_terms=False),
               inventory(["old", "old"]), dict(inventory(["old"]), dom="private meeting body"),
               inventory(["old"], enabled=False)]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ui.plan_ui(value, ["new"])

    def test_prepare_requires_exact_approval_and_matching_live_account_and_words(self):
        initial = inventory(["old"])
        plan = ui.plan_ui(initial, ["new"])
        for approval, current in [("", initial), (tx.plan_id(plan), inventory(["changed"])),
                                  (tx.plan_id(plan), inventory(["old"], identity="other-account"))]:
            with self.assertRaises(ValueError):
                ui.prepare_ui(plan, approval, current, self.root)
        self.assertFalse((self.root / "backups").exists())

    def test_ready_receipt_has_verified_old_word_backup_and_only_missing_actions(self):
        initial = inventory(["old"])
        plan = ui.plan_ui(initial, ["old", "new", "new"])
        ready = ui.prepare_ui(plan, tx.plan_id(plan), inventory(["old"]), self.root)
        self.assertEqual(ready["added"], ["new"])
        self.assertEqual(ready["after"]["words"], ["old", "new"])
        backup = Path(ready["backup"])
        self.assertEqual(json.loads(backup.read_text())["words"], ["old"])
        self.assertEqual(tx.sha(backup.read_bytes()), ready["backup_sha256"])
        self.assertNotIn("dom", backup.read_text())

    def test_verify_requires_all_old_and_approved_words_and_valid_backup(self):
        plan = ui.plan_ui(inventory(["old"]), ["new"])
        ready = ui.prepare_ui(plan, tx.plan_id(plan), inventory(["old"]), self.root)
        with self.assertRaises(ValueError):
            ui.verify_ui(ready, inventory(["new"]), self.root)
        with self.assertRaises(ValueError):
            ui.verify_ui(ready, inventory(["old", "new", "unexpected"]), self.root)
        result = ui.verify_ui(ready, inventory(["new", "old"]), self.root)
        self.assertEqual(result["status"], "verified")
        Path(ready["backup"]).write_text("corrupted")
        with self.assertRaises(ValueError):
            ui.verify_ui(ready, inventory(["old", "new"]), self.root)

    def test_changed_ready_actions_cannot_be_verified_with_original_plan_id(self):
        plan = ui.plan_ui(inventory(["old"]), ["approved"])
        ready = ui.prepare_ui(plan, tx.plan_id(plan), inventory(["old"]), self.root)
        ready["after"]["words"] = ["old", "not-approved"]
        ready["added"] = ["not-approved"]
        with self.assertRaisesRegex(ValueError, "approved|plan|receipt"):
            ui.verify_ui(ready, inventory(["old", "not-approved"]), self.root)

    def test_cli_plan_prepare_verify_do_not_claim_gui_was_written(self):
        import ddict
        old = self.root / "inventory.json"
        desired = self.root / "words.json"
        plan_path = self.root / "plans" / "ui.json"
        ready_path = self.root / "runs" / "ready.json"
        old.write_text(json.dumps(inventory(["old"])))
        desired.write_text('["new"]')
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                result = ddict.main(["ui-plan", "--inventory", str(old), "--words", str(desired),
                                     "--out", str(plan_path)])
            except SystemExit:
                result = -1
        self.assertEqual(result, 0, "ui-plan command must exist")
        approved = json.loads(plan_path.read_text())["id"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ddict.main(["ui-prepare", "--plan", str(plan_path), "--approve", approved,
                                        "--current", str(old), "--state", str(self.root),
                                        "--out", str(ready_path)]), 0)
        self.assertEqual(json.loads(ready_path.read_text())["status"], "ready")
        self.assertEqual(json.loads(old.read_text())["words"], ["old"])


if __name__ == "__main__":
    unittest.main()
