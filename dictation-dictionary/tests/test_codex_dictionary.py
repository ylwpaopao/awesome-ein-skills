import copy
import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import codex_dictionary as codex
except ModuleNotFoundError:
    codex = None


class CodexTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(codex, "Codex adapter is not implemented")

    def test_changes_only_array_value_preserving_comments_unicode_and_crlf(self):
        raw = ('# 保留\r\nmodel = "same"\r\n[desktop] # keep\r\n'
               'dictationDictionary = [\r\n "旧词", # inline\r\n "a]b",\r\n] # tail\r\n'
               'other = "keep"\r\n[other]\r\nvalue = 42\r\n').encode()
        old = '[\r\n "旧词", # inline\r\n "a]b",\r\n]'.encode()
        expected = raw.replace(old, '["旧词", "a]b", "项目甲"]'.encode(), 1)
        after = codex.patch_codex(raw, ["旧词", "a]b", "项目甲"])
        self.assertEqual(after, expected)
        self.assertEqual(codex.read_codex(after), ["旧词", "a]b", "项目甲"])

    def test_ignores_fake_headers_inside_multiline_strings_and_comments(self):
        text = '''example = """\n[desktop]\ndictationDictionary = ["fake"]\n"""
# [desktop]
[desktop]
dictationDictionary = ["real"]
unrelated = '[keep]'
'''
        self.assertEqual(codex.patch_codex(text.encode(), ["new"]),
                         text.replace('["real"]', '["new"]').encode())

    def test_supports_escaped_quotes_and_backslashes(self):
        raw = b'[desktop]\ndictationDictionary = ["old"]\n'
        terms = ['a"b', 'path\\name', "中文"]
        after = codex.patch_codex(raw, terms)
        self.assertEqual(tomllib.loads(after.decode())["desktop"]["dictationDictionary"], terms)

    def test_rejects_missing_key_non_string_values_and_unsupported_layout(self):
        samples = [b'[desktop]\nother = 1\n',
                   b'[desktop]\ndictationDictionary = [1]\n',
                   b'desktop = {dictationDictionary = ["x"]}\n',
                   b'[desktop]\n"dictationDictionary" = ["x"]\n',
                   b'[desktop]\ndictationDictionary = ["x"\n']
        for raw in samples:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                codex.patch_codex(raw, ["new"])

    def test_semantic_change_is_exactly_one_key(self):
        raw = b'model = "unchanged"\n[desktop]\ndictationDictionary = ["old"]\nflag = true\n'
        expected = copy.deepcopy(tomllib.loads(raw.decode()))
        expected["desktop"]["dictationDictionary"] = ["new"]
        self.assertEqual(tomllib.loads(codex.patch_codex(raw, ["new"]).decode()), expected)


if __name__ == "__main__":
    unittest.main()
