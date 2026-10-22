"""Synthetic MW-shaped data: no saved API keys or downloaded dictionary entries."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lookup.py"
SPEC = importlib.util.spec_from_file_location("mw_lookup", SCRIPT)
mw = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mw)


def sample():
    return [{
        "meta": {"id": "light:1", "syns": [["bright"], ["lightweight"]]},
        "hwi": {"hw": "light"},
        "fl": "adjective",
        "def": [{"sseq": [
            [["sense", {
                "sn": "1",
                "dt": [["text", "{bc}giving illumination"],
                       ["vis", [{"t": "A {it}light{/it} room.",
                                 "aq": {"auth": "Synthetic author"}}]]],
                "syn_list": [[{"wd": "bright"}, {"wd": "radiant"}],
                             [{"wd": "luminous", "wsls": {"wsl": "formal"}}]],
                "sim_list": [[{"wd": "sunny"}]],
                "phrase_list": [[{"wd": "full of light"}]],
                "rel_list": [[{"wd": "clear"}]],
                "near_list": [[{"wd": "dim"}]],
                "ant_list": [[{"wd": "dark"}]],
            }]],
            [["sense", {
                "sn": "2",
                "dt": [["text", "{bc}not heavy"],
                       ["vis", [{"t": "A light bag."}]]],
                "syn_list": [[{"wd": "lightweight"}]],
            }]],
        ]}],
        "shortdef": ["giving illumination", "not heavy"],
    }]


class SenseTests(unittest.TestCase):
    def test_senses_and_inner_word_groups_stay_separate(self):
        result = mw.parse_response(sample(), "light")
        senses = result["entries"][0]["senses"]
        self.assertEqual([s["number"] for s in senses], ["1", "2"])
        self.assertEqual(
            [[w["word"] for w in group] for group in senses[0]["synonyms"]],
            [["bright", "radiant"], ["luminous"]],
        )
        self.assertEqual(senses[1]["synonyms"][0][0]["word"], "lightweight")
        self.assertEqual(senses[0]["synonyms"][1][0]["labels"], ["formal"])
        self.assertEqual(senses[0]["examples"][0]["text"], "A light room.")
        self.assertEqual(senses[0]["examples"][0]["attribution"]["auth"], "Synthetic author")
        self.assertEqual(senses[1]["examples"][0]["text"], "A light bag.")

    def test_default_includes_sim_list_but_not_near_antonyms_or_related_words(self):
        sense = mw.parse_response(sample(), "light")["entries"][0]["senses"][0]
        self.assertEqual(sense["similar_words"][0][0]["word"], "sunny")
        self.assertEqual(sense["synonymous_phrases"][0][0]["word"], "full of light")
        for name in ("antonyms", "near_antonyms", "related_words", "phrases"):
            self.assertNotIn(name, sense)
        full = mw.parse_response(sample(), "light", all_relations=True)
        sense = full["entries"][0]["senses"][0]
        self.assertEqual(sense["near_antonyms"][0][0]["word"], "dim")
        self.assertEqual(sense["antonyms"][0][0]["word"], "dark")

    def test_nested_senses_divisions_and_variants_are_retained(self):
        payload = [{"meta": {"id": "move on:2"}, "fl": "verb", "def": [{
            "sseq": [[["bs", {"sense": {"sn": "1", "dt": [["text", "act"]]}}],
                      ["pseq", [["sense", {
                          "sn": "(1)", "dt": [["text", "{sx|advance||}"]],
                          "syn_list": [[{"wd": "go on", "wvrs": [{"wvl": "also", "wva": "continue"}]}]],
                          "sdsense": {"sd": "especially", "dt": [["text", "progress"],
                              ["vis", [{"t": "We move on."}]]]},
                      }]]]]],
        }]}]
        entry = mw.parse_response(payload, "move on")["entries"][0]
        self.assertEqual(len(entry["senses"]), 2)
        nested = entry["senses"][1]
        self.assertEqual(nested["definition"], "advance")
        self.assertEqual(nested["synonyms"][0][0]["variants"][0]["word"], "continue")
        self.assertEqual(nested["divided_sense"]["examples"][0]["text"], "We move on.")
        self.assertEqual(entry["thesaurus_url"], "https://www.merriam-webster.com/thesaurus/move%20on")

    def test_suggestions_empty_response_and_no_sense_data_are_distinct(self):
        suggestions = mw.parse_response(["practical", "practice"], "practcal")
        self.assertEqual(suggestions["status"], "suggestions")
        self.assertEqual(suggestions["suggestions"][0]["word"], "practical")
        self.assertEqual(mw.parse_response([], "unknown")["status"], "not_found")
        result = mw.parse_response([{"meta": {"id": "light", "syns": [["bright"], ["lightweight"]]}}], "light")
        self.assertEqual(result["entries"][0]["senses"], [])
        self.assertTrue(result["warnings"])

    def test_word_links_encode_reserved_characters_and_markup_keeps_text(self):
        self.assertEqual(mw.word_url("give & take"), "https://www.merriam-webster.com/thesaurus/give%20%26%20take")
        self.assertEqual(mw.clean_text("{bc}{sx|clear||} {amp} {it}simple{/it}"), "clear & simple")
        self.assertEqual(mw.clean_text("{d_link|see|look} {ldquo}word{rdquo}"), "see “word”")

    def test_markdown_keeps_examples_with_their_own_sense(self):
        rendered = mw.render_markdown(mw.parse_response(sample(), "light"))
        self.assertIn("[bright](https://www.merriam-webster.com/thesaurus/bright)", rendered)
        self.assertIn("**1**", rendered)
        self.assertIn("**2**", rendered)
        self.assertLess(rendered.index("A light room."), rendered.index("**2**"))
        self.assertGreater(rendered.index("A light bag."), rendered.index("**2**"))
        self.assertNotIn("dim", rendered)

    def test_entry_and_definition_labels_survive_both_output_formats(self):
        payload = sample()
        payload[0]["sls"] = ["chiefly British"]
        payload[0]["def"][0]["sls"] = ["slang"]
        result = mw.parse_response(payload, "light")
        sense = result["entries"][0]["senses"][0]
        self.assertEqual(sense["definition_labels"], ["slang"])
        rendered = mw.render_markdown(result)
        self.assertIn("chiefly British", rendered)
        self.assertIn("slang", rendered)


class RequestTests(unittest.TestCase):
    def test_query_and_key_are_encoded_in_the_official_request(self):
        body = json.dumps(sample()).encode()
        with patch.object(mw, "urlopen", return_value=io.BytesIO(body)) as call:
            data = mw.fetch_response("move on/over", "test-secret")
        self.assertEqual(data, sample())
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, "https://www.dictionaryapi.com/api/v3/references/thesaurus/json/move%20on%2Fover?key=test-secret")

    def test_errors_never_echo_url_key_or_server_response(self):
        secret = "test-secret-never-print"
        errors = [HTTPError("https://example.invalid/?key=" + secret, 403, secret, {}, None),
                  URLError("connection failed: " + secret)]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                with patch.object(mw, "urlopen", side_effect=error):
                    with self.assertRaises(mw.LookupFailure) as caught:
                        mw.fetch_response("light", secret)
                self.assertNotIn(secret, str(caught.exception))
        with patch.object(mw, "urlopen", return_value=io.BytesIO(secret.encode())):
            with self.assertRaises(mw.LookupFailure) as caught:
                mw.fetch_response("light", secret)
        self.assertNotIn(secret, str(caught.exception))

    def test_environment_precedes_keychain_and_is_not_logged(self):
        with patch.dict(os.environ, {mw.KEY_ENV: "private-example"}, clear=True):
            with patch.object(mw.subprocess, "run") as keychain:
                key, source = mw.load_key()
        self.assertEqual((key, source), ("private-example", "environment"))
        keychain.assert_not_called()

    def test_keychain_lookup_uses_service_and_current_account(self):
        process = subprocess.CompletedProcess([], 0, "keychain-secret\n", "")
        with patch.dict(os.environ, {}, clear=True), patch.object(mw.sys, "platform", "darwin"):
            with patch.object(mw.getpass, "getuser", return_value="test-user"):
                with patch.object(mw.subprocess, "run", return_value=process) as call:
                    key, source = mw.load_key()
        self.assertEqual((key, source), ("keychain-secret", "macos-keychain"))
        self.assertEqual(call.call_args.args[0], ["/usr/bin/security", "find-generic-password", "-a", "test-user", "-s", mw.KEYCHAIN_SERVICE, "-w"])

    def test_cli_json_and_check_key_do_not_disclose_credentials(self):
        body = json.dumps(sample()).encode()
        with patch.dict(os.environ, {mw.KEY_ENV: "test-private-key"}, clear=True):
            with patch.object(mw.sys, "argv", [str(SCRIPT), "light", "--format", "json"]):
                with patch.object(mw, "urlopen", return_value=io.BytesIO(body)):
                    with patch("sys.stdout", new_callable=io.StringIO) as output:
                        self.assertEqual(mw.main(), 0)
                        result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "found")
            self.assertNotIn("test-private-key", output.getvalue())
            with patch.object(mw.sys, "argv", [str(SCRIPT), "--check-key"]):
                with patch.object(mw, "fetch_response") as fetch:
                    with patch("sys.stdout", new_callable=io.StringIO) as output:
                        self.assertEqual(mw.main(), 0)
            self.assertEqual(json.loads(output.getvalue()), {"configured": True, "source": "environment"})
            fetch.assert_not_called()

    def test_missing_key_produces_an_actionable_error(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(mw.sys, "platform", "linux"):
            with self.assertRaises(mw.LookupFailure) as error:
                mw.load_key()
        self.assertIn(mw.KEY_ENV, str(error.exception))

    def test_locked_keychain_is_not_reported_as_an_unconfigured_key(self):
        process = subprocess.CompletedProcess([], 36, "", "denied: test-secret")
        with patch.dict(os.environ, {}, clear=True), patch.object(mw.sys, "platform", "darwin"):
            with patch.object(mw.subprocess, "run", return_value=process):
                with self.assertRaises(mw.LookupFailure) as error:
                    mw.load_key()
        self.assertIn("无法读取 macOS 钥匙串", str(error.exception))
        self.assertNotIn("test-secret", str(error.exception))

    def test_chinese_input_routes_to_agent_before_any_request(self):
        with patch.object(mw, "fetch_response") as fetch:
            with patch.object(mw, "load_key") as key:
                with patch.object(mw.sys, "argv", [str(SCRIPT), "切实可行"]):
                    with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                        self.assertEqual(mw.main(), 2)
        self.assertIn("英文候选", stderr.getvalue())
        fetch.assert_not_called()
        key.assert_not_called()


class RuntimeTests(unittest.TestCase):
    def test_lookup_runs_without_syncing_the_callers_python_project(self):
        with tempfile.TemporaryDirectory(prefix="mw-skill-") as folder:
            root = Path(folder)
            project = root / "pyproject.toml"
            original = ('[project]\nname="unrelated-project"\nversion="0.0.0"\n'
                        'requires-python=">=3.11"\n'
                        'dependencies=["nonexistent-mw-project-pkg==0.0.0"]\n')
            project.write_text(original)
            local_script = root / "lookup.py"
            local_script.write_bytes(SCRIPT.read_bytes())
            result = subprocess.run(
                ["uv", "run", "--cache-dir", str(root / "uv-cache"), "--offline", str(local_script), "--help"],
                cwd=root, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage:", result.stdout)
            self.assertEqual(project.read_text(), original)
            self.assertFalse((root / ".venv").exists())


if __name__ == "__main__":
    unittest.main()
