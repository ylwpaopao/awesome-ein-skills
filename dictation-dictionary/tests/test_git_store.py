import json
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import transactions as tx
from vocabulary import active_words, library_bytes, merge_entries
try:
    import git_store as store
except ModuleNotFoundError:
    store = None


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(store, "Git store is not implemented")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / "remote.git"
        self.remote.mkdir()
        git(self.remote, "init", "--bare", "-b", "main")
        self.repo = self.root / "one"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        self.configure(self.repo)
        git(self.repo, "remote", "add", "origin", str(self.remote))
        self.library = merge_entries({"version": 1, "entries": []}, [{"term": "old"}])
        self.write_commit(self.repo, self.library)
        git(self.repo, "push", "-u", "origin", "main")
        self.other = self.root / "two"
        subprocess.run(["git", "clone", str(self.remote), str(self.other)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.configure(self.other)
        self.state = self.root / "state"

    def configure(self, repo):
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.invalid")

    def write_commit(self, repo, library):
        (repo / "vocabulary.json").write_bytes(library_bytes(library))
        git(repo, "add", "--", "vocabulary.json")
        git(repo, "commit", "-m", "fixture change")

    def test_fetch_reads_new_remote_without_changing_local_library(self):
        remote_lib = merge_entries(self.library, [{"term": "remote"}])
        self.write_commit(self.other, remote_lib)
        git(self.other, "push")
        before = (self.repo / "vocabulary.json").read_bytes()
        fetched = store.fetch_remote_library(self.repo)
        self.assertEqual(active_words(fetched["library"]), ["old", "remote"])
        self.assertEqual((self.repo / "vocabulary.json").read_bytes(), before)

    def test_approved_update_backs_up_and_pushes_only_vocabulary(self):
        desired = merge_entries(self.library, [{"term": "new"}])
        plan = store.plan_store_update(self.repo, desired)
        with self.assertRaises(ValueError):
            store.apply_store_update(plan, "", self.state)
        result = store.apply_store_update(plan, tx.plan_id(plan), self.state)
        self.assertEqual(result["status"], "pushed")
        self.assertEqual(json.loads(git(self.remote, "show", "main:vocabulary.json")), desired)
        self.assertEqual(Path(result["local"]["backup"]).read_bytes(), library_bytes(self.library))
        self.assertEqual(git(self.remote, "ls-tree", "-r", "--name-only", "main"), "vocabulary.json")

    def test_remote_advancing_after_preview_rejects_before_local_write(self):
        desired = merge_entries(self.library, [{"term": "local"}])
        plan = store.plan_store_update(self.repo, desired)
        remote_lib = merge_entries(self.library, [{"term": "remote"}])
        self.write_commit(self.other, remote_lib)
        git(self.other, "push")
        with self.assertRaises(ValueError):
            store.apply_store_update(plan, tx.plan_id(plan), self.state)
        self.assertEqual(json.loads((self.repo / "vocabulary.json").read_text()), self.library)
        self.assertEqual(json.loads(git(self.remote, "show", "main:vocabulary.json")), remote_lib)

    def test_fast_forward_keeps_remote_metadata_and_new_remote_words(self):
        remote_lib = merge_entries(self.library, [{"term": "old", "enabled": False}, {"term": "remote"}])
        self.write_commit(self.other, remote_lib)
        git(self.other, "push")
        desired = merge_entries(self.library, [{"term": "local"}])
        plan = store.plan_store_update(self.repo, desired)
        self.assertEqual(active_words(plan["after"]["library"]), ["remote", "local"])
        store.apply_store_update(plan, tx.plan_id(plan), self.state)
        actual = json.loads(git(self.remote, "show", "main:vocabulary.json"))
        self.assertEqual(active_words(actual), ["remote", "local"])
        self.assertFalse(actual["entries"][0]["enabled"])

    def test_local_source_update_preserves_new_remote_exclusions_and_enabled_state(self):
        remote_lib = merge_entries(self.library, [{"term": "old", "enabled": False,
                                                   "excluded_targets": ["codex", "typeless"]}])
        self.write_commit(self.other, remote_lib)
        git(self.other, "push")
        desired = merge_entries(self.library, [{"term": "old", "sources": [{"url": "https://example.com/new"}]}])
        plan = store.plan_store_update(self.repo, desired)
        item = plan["after"]["library"]["entries"][0]
        self.assertEqual(item["excluded_targets"], ["codex", "typeless"])
        self.assertFalse(item["enabled"])
        self.assertEqual(item["sources"], [{"url": "https://example.com/new"}])

    def test_concurrent_new_term_with_conflicting_policy_refuses_to_clear_remote_exclusions(self):
        remote_lib = merge_entries(self.library, [{"term": "concurrent",
                                                   "excluded_targets": ["codex", "typeless"]}])
        self.write_commit(self.other, remote_lib)
        git(self.other, "push")
        desired = merge_entries(self.library, [{"term": "concurrent",
                                               "sources": [{"url": "https://example.com/new"}]}])
        before = (self.repo / "vocabulary.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "conflicting.*policy"):
            store.plan_store_update(self.repo, desired)
        self.assertEqual((self.repo / "vocabulary.json").read_bytes(), before)
        self.assertEqual(json.loads(git(self.remote, "show", "main:vocabulary.json")), remote_lib)

    def test_unrelated_staged_file_prevents_any_commit(self):
        (self.repo / "other.txt").write_text("keep this separate")
        git(self.repo, "add", "other.txt")
        with self.assertRaises(ValueError):
            store.plan_store_update(self.repo, self.library)

    def test_push_failure_keeps_local_commit_and_backup(self):
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o700)
        desired = merge_entries(self.library, [{"term": "local"}])
        plan = store.plan_store_update(self.repo, desired)
        result = store.apply_store_update(plan, tx.plan_id(plan), self.state)
        self.assertEqual(result["status"], "push_failed")
        self.assertTrue(Path(result["local"]["backup"]).exists())
        self.assertEqual(json.loads(git(self.remote, "show", "main:vocabulary.json")), self.library)
        self.assertEqual(active_words(json.loads(git(self.repo, "show", "HEAD:vocabulary.json"))), ["old", "local"])

    def test_missing_remote_and_offline_remote_do_not_change_library(self):
        before = (self.repo / "vocabulary.json").read_bytes()
        git(self.repo, "remote", "remove", "origin")
        with self.assertRaises(ValueError):
            store.fetch_remote_library(self.repo)
        git(self.repo, "remote", "add", "origin", str(self.root / "missing.git"))
        with self.assertRaises(ValueError):
            store.fetch_remote_library(self.repo)
        self.assertEqual((self.repo / "vocabulary.json").read_bytes(), before)

    def test_empty_store_initialization_has_no_implicit_dictionary_write(self):
        empty = self.root / "empty.git"
        empty.mkdir()
        git(empty, "init", "--bare", "-b", "main")
        path = self.root / "new-store"
        store.initialize_store(path, str(empty))
        self.configure(path)
        self.assertFalse((path / "vocabulary.json").exists())
        plan = store.plan_store_update(path, self.library)
        result = store.apply_store_update(plan, tx.plan_id(plan), self.state)
        self.assertEqual(result["status"], "pushed")
        self.assertEqual(json.loads(git(empty, "show", "main:vocabulary.json")), self.library)

    def test_public_github_remote_is_rejected_before_fetch(self):
        git(self.repo, "remote", "set-url", "origin", "https://github.com/example/vocabulary.git")
        with patch.object(store, "_github_private", return_value=False):
            with self.assertRaisesRegex(ValueError, "private"):
                store.fetch_remote_library(self.repo)

    def test_different_or_multiple_push_destinations_are_rejected(self):
        other_remote = self.root / "unexpected.git"
        other_remote.mkdir()
        git(other_remote, "init", "--bare", "-b", "main")
        git(self.repo, "remote", "set-url", "--push", "origin", str(other_remote))
        with self.assertRaisesRegex(ValueError, "push"):
            store.plan_store_update(self.repo, merge_entries(self.library, [{"term": "private-new"}]))
        self.assertEqual(git(other_remote, "show-ref", "--heads") if (other_remote / "refs/heads/main").exists() else "", "")
        git(self.repo, "remote", "set-url", "--push", "origin", str(self.remote))
        git(self.repo, "remote", "set-url", "--add", "--push", "origin", str(other_remote))
        with self.assertRaisesRegex(ValueError, "push"):
            store.inspect_store(self.repo)

    def test_push_destination_changed_after_preview_rejects_before_local_write(self):
        desired = merge_entries(self.library, [{"term": "private-new"}])
        plan = store.plan_store_update(self.repo, desired)
        other_remote = self.root / "unexpected.git"
        other_remote.mkdir()
        git(other_remote, "init", "--bare", "-b", "main")
        git(self.repo, "remote", "set-url", "--push", "origin", str(other_remote))
        before = (self.repo / "vocabulary.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "push"):
            store.apply_store_update(plan, tx.plan_id(plan), self.state)
        self.assertEqual((self.repo / "vocabulary.json").read_bytes(), before)
        self.assertFalse((self.state / "backups").exists())
        self.assertFalse((other_remote / "refs/heads/main").exists())

    def test_reviewed_explicit_origin_pushurl_is_not_rewritten_as_a_raw_url(self):
        other_remote = self.root / "unexpected.git"
        other_remote.mkdir()
        git(other_remote, "init", "--bare", "-b", "main")
        git(self.repo, "remote", "set-url", "--push", "origin", str(self.remote))
        git(self.repo, "config", "url." + str(other_remote) + ".pushInsteadOf", str(self.remote))
        desired = merge_entries(self.library, [{"term": "private-new"}])
        plan = store.plan_store_update(self.repo, desired)
        result = store.apply_store_update(plan, tx.plan_id(plan), self.state)
        self.assertEqual(result["status"], "pushed")
        self.assertEqual(json.loads(git(self.remote, "show", "main:vocabulary.json")), desired)
        self.assertFalse((other_remote / "refs/heads/main").exists())

    def test_unchanged_store_has_no_commit_or_backup(self):
        before = git(self.repo, "rev-parse", "HEAD")
        plan = store.plan_store_update(self.repo, self.library)
        result = store.apply_store_update(plan, tx.plan_id(plan), self.state)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertFalse((self.state / "backups").exists())

    def test_cli_git_plan_is_read_only_and_reports_push_result(self):
        import ddict
        desired = self.root / "desired.json"
        desired.write_bytes(library_bytes(merge_entries(self.library, [{"term": "new"}])))
        plan_path = self.root / "plans" / "git.json"
        before = git(self.repo, "rev-parse", "HEAD")
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                result = ddict.main(["git-plan", "--repo", str(self.repo), "--desired", str(desired),
                                     "--out", str(plan_path)])
            except SystemExit:
                result = -1
        self.assertEqual(result, 0, "git-plan command must exist")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        approved = json.loads(plan_path.read_text())["id"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(ddict.main(["git-apply", "--plan", str(plan_path), "--approve", approved,
                                         "--state", str(self.state)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "pushed")


if __name__ == "__main__":
    unittest.main()
