import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "workflow_files", Path(__file__).parents[1] / "scripts" / "workflow_files.py"
)
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)
PDF = b"%PDF-1.4\nfile lifecycle fixture, not a rendering test\n%%EOF\n"


class WorkflowFilesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.downloads = self.root / "Downloads"
        self.downloads.mkdir()
        self.stored = self.root / "Zotero" / "storage" / "ABCD1234" / "paper.pdf"
        self.stored.parent.mkdir(parents=True)

    def prepare(self):
        result = workflow.prepare(
            "https://doi.org/10.5555%2Ffixture", downloads=self.downloads, parent=self.root
        )
        self.session = Path(result["session"])
        return result

    def registered(self):
        result = self.prepare()
        self.source = Path(result["download_directory"]) / "paper.pdf"
        self.source.write_bytes(PDF)
        workflow.register(self.session, str(self.source))
        shutil.copy2(self.source, self.stored)

    def test_normalizes_supported_doi_forms(self):
        for value in (" 10.5555/fixture ", "doi:10.5555/fixture", "https://doi.org/10.5555%2Ffixture"):
            self.assertEqual(workflow.normalize_doi(value), "10.5555/fixture")

    def test_invalid_doi_does_not_create_task_files(self):
        before = set(self.root.iterdir())
        with self.assertRaises(ValueError):
            workflow.prepare("https://unrelated.example/paper", parent=self.root)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_extracts_primary_article_metadata_instead_of_references(self):
        page = {
            "url": "https://publisher.example/article/123",
            "title": "The intended paper",
            "metadata": [{"name": "citation_doi", "content": "10.5555/intended"}],
            "references": ["10.5555/unrelated"],
        }
        self.assertEqual(workflow.resolve_primary_doi(page)["doi"], "10.5555/intended")

    def test_accepts_visible_primary_doi_when_metadata_is_absent(self):
        self.assertEqual(
            workflow.resolve_primary_doi({"primary_doi": "https://doi.org/10.5555/header"})["doi"],
            "10.5555/header",
        )

    def test_missing_primary_doi_reports_failure(self):
        with self.assertRaisesRegex(ValueError, "No primary article DOI"):
            workflow.resolve_primary_doi({"references": ["10.5555/reference-only"]})

    def test_conflicting_primary_dois_report_failure(self):
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            workflow.resolve_primary_doi({"metadata": [
                {"name": "citation_doi", "content": "10.5555/first"},
                {"name": "prism.doi", "content": "10.5555/second"},
            ]})

    def test_verified_header_resolves_conflicting_metadata(self):
        result = workflow.resolve_primary_doi({
            "primary_doi": "https://doi.org/10.5555/current-paper",
            "metadata": [
                {"name": "citation_doi", "content": "10.5555/stale"},
                {"name": "prism.doi", "content": "10.5555/current-paper"},
            ],
        })
        self.assertEqual(result["doi"], "10.5555/current-paper")

    def test_rejects_html_disguised_as_pdf(self):
        result = self.prepare()
        source = Path(result["download_directory"]) / "paper.pdf"
        source.write_bytes(b"<html>Login required</html>")
        with self.assertRaisesRegex(ValueError, "PDF signature"):
            workflow.register(self.session, str(source))
        self.assertTrue(source.exists())

    def test_preserves_preexisting_download(self):
        old = self.downloads / "paper.pdf"
        old.write_bytes(PDF)
        self.prepare()
        with self.assertRaisesRegex(ValueError, "existed"):
            workflow.register(self.session, str(old))
        self.assertEqual(old.read_bytes(), PDF)

    def test_rejects_untracked_external_file(self):
        self.prepare()
        unrelated = self.root / "personal.pdf"
        unrelated.write_bytes(PDF)
        with self.assertRaisesRegex(ValueError, "task directory or Downloads"):
            workflow.register(self.session, str(unrelated))
        self.assertTrue(unrelated.exists())

    def test_requires_actual_reader_verification(self):
        self.registered()
        with self.assertRaisesRegex(ValueError, "readable first page"):
            workflow.finish(self.session, str(self.stored))
        self.assertTrue(self.source.exists())

    def test_changed_source_is_preserved(self):
        self.registered()
        self.source.write_bytes(PDF + b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            workflow.finish(self.session, str(self.stored), reader_verified=True)
        self.assertTrue(self.source.exists())

    def test_mismatched_zotero_copy_is_preserved(self):
        self.registered()
        self.stored.write_bytes(PDF + b"different paper")
        with self.assertRaisesRegex(ValueError, "does not match"):
            workflow.finish(self.session, str(self.stored), reader_verified=True)
        self.assertTrue(self.source.exists())
        self.assertTrue(self.stored.exists())

    def test_rejects_linked_file_and_hardlink(self):
        self.registered()
        with self.assertRaises(ValueError):
            workflow.finish(self.session, str(self.source), reader_verified=True)
        self.stored.unlink()
        self.stored.hardlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "independent"):
            workflow.finish(self.session, str(self.stored), reader_verified=True)
        self.assertTrue(self.source.exists())

    def test_success_cleans_only_task_download_and_keeps_stored_copy(self):
        unrelated = self.downloads / "leave-me.pdf"
        unrelated.write_bytes(PDF)
        self.registered()
        result = workflow.finish(self.session, str(self.stored), reader_verified=True)
        self.assertEqual(result["deleted_download"], str(self.source))
        self.assertFalse(self.source.exists())
        self.assertFalse(self.session.parent.exists())
        self.assertEqual(self.stored.read_bytes(), PDF)
        self.assertEqual(unrelated.read_bytes(), PDF)

    def test_accepts_new_browser_download(self):
        self.prepare()
        source = self.downloads / "new-paper.pdf"
        source.write_bytes(PDF)
        workflow.register(self.session, str(source))
        shutil.copy2(source, self.stored)
        workflow.finish(self.session, str(self.stored), reader_verified=True)
        self.assertFalse(source.exists())
        self.assertTrue(self.downloads.is_dir())
        self.assertEqual(self.stored.read_bytes(), PDF)

    def test_cleans_registered_task_cache_and_staged_pdf(self):
        result = self.prepare()
        cache = self.root / "new-browser-cache.pdf"
        cache.write_bytes(PDF)
        source = Path(result["download_directory"]) / "paper.pdf"
        shutil.copy2(cache, source)
        workflow.register(self.session, str(source), cache_source=str(cache))
        shutil.copy2(source, self.stored)
        cleaned = workflow.finish(self.session, str(self.stored), reader_verified=True)
        self.assertEqual(cleaned["deleted_cache"], str(cache))
        self.assertFalse(cache.exists())
        self.assertFalse(source.exists())
        self.assertEqual(self.stored.read_bytes(), PDF)

    def test_preserves_cache_from_before_task(self):
        cache = self.root / "old-browser-cache.pdf"
        cache.write_bytes(PDF)
        result = self.prepare()
        source = Path(result["download_directory"]) / "paper.pdf"
        shutil.copy2(cache, source)
        with self.assertRaisesRegex(ValueError, "predates"):
            workflow.register(self.session, str(source), cache_source=str(cache))
        self.assertTrue(cache.exists())
        self.assertTrue(source.exists())

    def test_changed_cache_prevents_any_download_deletion(self):
        result = self.prepare()
        cache = self.root / "task-browser-cache.pdf"
        cache.write_bytes(PDF)
        source = Path(result["download_directory"]) / "paper.pdf"
        shutil.copy2(cache, source)
        workflow.register(self.session, str(source), cache_source=str(cache))
        shutil.copy2(source, self.stored)
        cache.write_bytes(PDF + b"changed")
        with self.assertRaisesRegex(ValueError, "Cache file changed"):
            workflow.finish(self.session, str(self.stored), reader_verified=True)
        self.assertTrue(cache.exists())
        self.assertTrue(source.exists())


class DomainRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.registry = Path(self.temporary.name) / "domains.json"
        self.registry.write_text(json.dumps({"schema_version": 1, "domains": [{
            "url": "https://sci-hub.example/", "last_result": "user-reported", "last_verified_at": None,
        }]}))

    def test_user_report_is_not_verification(self):
        entry = workflow.read_domains(self.registry)["domains"][0]
        self.assertEqual(entry["last_result"], "user-reported")
        self.assertIsNone(entry["last_verified_at"])

    def test_policy_and_network_failures_do_not_claim_availability(self):
        for result in ("network-unavailable", "policy-blocked"):
            entry = workflow.record_domain("https://sci-hub.example", result, registry=self.registry)
            self.assertEqual(entry["last_result"], result)
            self.assertIsNone(entry["last_verified_at"])

    def test_records_new_domain_without_reordering_or_duplication(self):
        workflow.record_domain("https://new.example/", "available", registry=self.registry)
        workflow.record_domain("https://new.example", "network-unavailable", registry=self.registry)
        entries = workflow.read_domains(self.registry)["domains"]
        self.assertEqual([entry["url"] for entry in entries], ["https://sci-hub.example/", "https://new.example/"])
        self.assertIsNotNone(entries[1]["last_verified_at"])
        self.assertEqual(entries[1]["last_result"], "network-unavailable")

    def test_rejects_non_root_or_insecure_urls_without_mutating_registry(self):
        before = self.registry.read_bytes()
        for url in ("http://sci-hub.example/", "https://sci-hub.example/article", "https://user:secret@sci-hub.example/"):
            with self.assertRaises(ValueError):
                workflow.record_domain(url, "available", registry=self.registry)
        self.assertEqual(self.registry.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
