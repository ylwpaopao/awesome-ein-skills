#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Query the official MW Thesaurus API without flattening sense or word groups.

Standard library only. Run with: uv run /absolute/path/to/lookup.py WORD
"""

import argparse
import getpass
import html
import json
import os
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


KEY_ENV = "MERRIAM_WEBSTER_THESAURUS_API_KEY"
KEYCHAIN_SERVICE = "merriam-webster-thesaurus"
API_BASE = "https://www.dictionaryapi.com/api/v3/references/thesaurus/json/"
DEFAULT_RELATIONS = {
    "syn_list": "synonyms",
    "sim_list": "similar_words",
    "phrase_list": "synonymous_phrases",
}
EXTRA_RELATIONS = {
    "rel_list": "related_words",
    "ant_list": "antonyms",
    "near_list": "near_antonyms",
    "opp_list": "opposite_words",
}
RELATION_LABELS = {
    "synonyms": "同义词",
    "similar_words": "同义与近义词",
    "synonymous_phrases": "同义短语",
    "related_words": "相关词",
    "antonyms": "反义词",
    "near_antonyms": "近反义词",
    "opposite_words": "反义与近反义词",
}


class LookupFailure(Exception):
    """A user-facing error that contains no credentials or request URLs."""


def clean_text(value):
    """Remove MW formatting while keeping the visible text of link tokens."""
    symbols = {
        "bc": ": ", "amp": "&", "nbsp": " ", "ldquo": "“", "rdquo": "”",
        "lsquo": "‘", "rsquo": "’", "mdash": "—", "ndash": "–",
        "p_br": " ", "gloss": " ",
    }

    def replace(match):
        name, *parts = match.group(1).split("|")
        if name in symbols:
            return symbols[name]
        # {sx|visible text|target|sense}, {d_link|visible text|target}, etc.
        return parts[0] if parts else ""

    text = re.sub(r"\{([^{}]+)\}", replace, str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip().lstrip(": ")


def word_url(word, section="thesaurus"):
    return f"https://www.merriam-webster.com/{section}/{quote(word, safe='')}"


def labels(value):
    if isinstance(value, str):
        return [clean_text(value)] if value else []
    if isinstance(value, dict):
        return labels(value.get("wsl", ""))
    if isinstance(value, list):
        return [label for item in value for label in labels(item)]
    return []


def word_groups(groups):
    result = []
    for group in groups or []:
        words = []
        for item in group:
            if not isinstance(item, dict) or not item.get("wd"):
                continue
            word = clean_text(item["wd"])
            variants = []
            for field, name, label in (("wvrs", "wva", "wvl"),
                                       ("wvbvrs", "wvbva", "wvbvl")):
                for variant in item.get(field, []):
                    if variant.get(name):
                        variants.append({"word": clean_text(variant[name]),
                                         "label": clean_text(variant.get(label, ""))})
            words.append({"word": word, "labels": labels(item.get("wsls")),
                          "variants": variants, "thesaurus_url": word_url(word),
                          "dictionary_url": word_url(word, "dictionary")})
        if words:
            result.append(words)
    return result


def iter_senses(node, path=()):
    """Walk tagged sseq/pseq arrays, retaining each individual sense's path."""
    if not isinstance(node, list):
        return
    if len(node) == 2 and isinstance(node[0], str):
        tag, payload = node
        if tag in ("sense", "sen") and isinstance(payload, dict):
            yield payload, path, tag
        elif tag == "bs" and isinstance(payload, dict):
            if isinstance(payload.get("sense"), dict):
                yield payload["sense"], path, "bs"
        elif tag == "pseq":
            yield from iter_senses(payload, path)
        return
    for index, child in enumerate(node):
        yield from iter_senses(child, path + (index,))


def normalize_sense(sense, path, kind, source_url, all_relations):
    definitions, examples = [], []
    for part in sense.get("dt", []):
        if not isinstance(part, list) or len(part) != 2:
            continue
        if part[0] == "text":
            definitions.append(clean_text(part[1]))
        elif part[0] == "vis":
            for example in part[1]:
                if isinstance(example, dict) and example.get("t"):
                    examples.append({"text": clean_text(example["t"]),
                                     "attribution": example.get("aq", {}),
                                     "source_url": source_url})
    result = {
        "number": sense.get("sn", ""), "path": list(path), "kind": kind,
        "definition": " ".join(definitions), "examples": examples,
        "labels": labels(sense.get("lbs")) + labels(sense.get("sls")),
        "source_url": source_url,
    }
    relations = DEFAULT_RELATIONS | (EXTRA_RELATIONS if all_relations else {})
    for original, name in relations.items():
        if original in sense:
            result[name] = word_groups(sense[original])
    if isinstance(sense.get("sdsense"), dict):
        divided = sense["sdsense"]
        result["divided_sense"] = normalize_sense(
            divided, path, "sdsense", source_url, all_relations)
        result["divided_sense"]["divider"] = clean_text(divided.get("sd", ""))
    return result


def parse_response(data, query, all_relations=False):
    if not isinstance(data, list):
        raise LookupFailure("API 未返回词条列表；请检查 Key 是否属于 Collegiate Thesaurus。")
    result = {"query": query, "source": "Merriam-Webster's Collegiate Thesaurus",
              "status": "not_found", "entries": [], "warnings": []}
    if not data:
        return result
    if all(isinstance(item, str) for item in data):
        result["status"] = "suggestions"
        result["suggestions"] = [{"word": item, "thesaurus_url": word_url(item)} for item in data]
        return result
    if not all(isinstance(item, dict) for item in data):
        raise LookupFailure("API 返回了无法识别的词条结构。")
    result["status"] = "found"
    for item in data:
        entry_id = item.get("meta", {}).get("id", query)
        headword = clean_text(item.get("hwi", {}).get("hw", "")).replace("*", "")
        headword = headword or re.sub(r":\d+$", "", entry_id)
        source_url = word_url(headword)
        senses = []
        for definition_index, definition in enumerate(item.get("def", [])):
            for sense, path, kind in iter_senses(definition.get("sseq", [])):
                normalized = normalize_sense(sense, (definition_index,) + path,
                                             kind, source_url, all_relations)
                normalized["verb_divider"] = clean_text(definition.get("vd", ""))
                normalized["definition_labels"] = labels(definition.get("sls"))
                senses.append(normalized)
        entry = {
            "id": entry_id, "headword": headword, "part_of_speech": item.get("fl", ""),
            "labels": labels(item.get("lbs")) + labels(item.get("sls")),
            "thesaurus_url": source_url, "dictionary_url": word_url(headword, "dictionary"),
            "short_definitions": [clean_text(text) for text in item.get("shortdef", [])],
            "senses": senses,
        }
        # meta.syns/ants do not carry the full sense/definition/example relationship.
        if not senses:
            result["warnings"].append(f"{headword}: 未提供可解析的义项；未用 meta.syns 猜测分组。")
        result["entries"].append(entry)
    return result


def load_key():
    key = os.environ.get(KEY_ENV, "").strip()
    if key:
        return key, "environment"
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-a", getpass.getuser(),
                 "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip(), "macos-keychain"
            if result.returncode not in (0, 44):
                raise LookupFailure(
                    f"无法读取 macOS 钥匙串（状态 {result.returncode}）；请解锁或允许访问，或通过 {KEY_ENV} 注入 Key。")
        except subprocess.TimeoutExpired:
            raise LookupFailure("读取 macOS 钥匙串超时；请检查系统访问提示或解锁钥匙串。") from None
        except OSError:
            raise LookupFailure(f"无法读取 macOS 钥匙串；可通过 {KEY_ENV} 注入 Key。") from None
    raise LookupFailure(f"未找到 Thesaurus Key。请设置环境变量 {KEY_ENV}，或按 references/setup.md 存入 macOS 钥匙串。")


def fetch_response(word, key):
    request = Request(API_BASE + quote(word, safe="") + "?" + urlencode({"key": key}),
                      headers={"Accept": "application/json", "User-Agent": "merriam-webster-skill/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read()
    except HTTPError as error:
        error.close()
        if error.code in (401, 403):
            message = "API 拒绝访问；请确认 Key 有效且订阅了 Collegiate Thesaurus。"
        elif error.code == 429:
            message = "API 请求额度已用完或被限流；请稍后再试。"
        else:
            message = f"API 请求失败（HTTP {error.code}）。"
        raise LookupFailure(message) from None
    except (URLError, OSError, TimeoutError, ValueError):
        raise LookupFailure("无法连接 Merriam-Webster API；请检查网络、TLS 或代理设置。") from None
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        # Invalid MW keys can produce a plain-text error with HTTP 200.
        raise LookupFailure("API 未返回 JSON；请确认 Key 有效且订阅了 Collegiate Thesaurus。") from None
    if not isinstance(data, list):
        raise LookupFailure("API 未返回词条列表；请确认 Key 属于 Collegiate Thesaurus。")
    return data


def markdown_text(text):
    return re.sub(r"([\\`*\[\]<>_])", r"\\\1", text)


def render_word(word):
    text = f"[{markdown_text(word['word'])}]({word['thesaurus_url']})"
    if word["labels"]:
        text += "（" + "、".join(markdown_text(label) for label in word["labels"]) + "）"
    if word["variants"]:
        text += "（" + "; ".join(markdown_text((v["label"] + " " + v["word"]).strip())
                                 for v in word["variants"]) + "）"
    return text


def render_sense(sense, fallback_number, indent=""):
    number = sense.get("number") or fallback_number
    label = "、".join(sense["labels"])
    context = " / ".join(filter(None, [sense.get("verb_divider"),
                                       "、".join(sense.get("definition_labels", [])), label]))
    lines = [f"{indent}**{markdown_text(str(number))}** {markdown_text(sense['definition'])}" +
             (f"（{markdown_text(context)}）" if context else "")]
    for name, label in RELATION_LABELS.items():
        for index, group in enumerate(sense.get(name, []), 1):
            group_label = f" {index}" if len(sense[name]) > 1 else ""
            lines.append(f"{indent}- {label}{group_label}：" + "、".join(render_word(word) for word in group))
    for example in sense["examples"]:
        attribution = example["attribution"]
        author = attribution.get("auth", "") if isinstance(attribution, dict) else ""
        suffix = f" — {markdown_text(author)}" if author else ""
        lines.append(f"{indent}- 词典例句：{markdown_text(example['text'])}{suffix}")
    if "divided_sense" in sense:
        divided = sense["divided_sense"]
        lines.extend(render_sense(divided, divided.get("divider") or "细分义项", indent))
    return lines


def render_markdown(result):
    lines = ["来源：Merriam-Webster’s Collegiate Thesaurus", ""]
    if result["status"] == "not_found":
        lines.append("未找到该词条。")
    elif result["status"] == "suggestions":
        lines.append("未找到精确词条；以下仅为拼写建议：")
        lines.extend(f"- [{markdown_text(item['word'])}]({item['thesaurus_url']})"
                     for item in result["suggestions"])
    for entry in result["entries"]:
        entry_labels = "、".join(markdown_text(label) for label in entry["labels"])
        heading = (f"[{markdown_text(entry['headword'])}]({entry['thesaurus_url']})"
                   f" · {markdown_text(entry['part_of_speech'])}")
        if entry_labels:
            heading += f"（{entry_labels}）"
        lines.extend([heading + f" · [词典释义]({entry['dictionary_url']})", ""])
        for index, sense in enumerate(entry["senses"], 1):
            lines.extend(render_sense(sense, str(index)))
            lines.append("")
    lines.extend(result.get("warnings", []))
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("word", nargs="?", help="由 Agent 选定的英文单词或短语")
    parser.add_argument("--format", choices=("markdown", "json", "raw"), default="markdown")
    parser.add_argument("--all-relations", action="store_true", help="同时保留相关词、反义词与近反义词")
    parser.add_argument("--check-key", action="store_true", help="仅检查凭据来源，不显示 Key、不请求 API")
    args = parser.parse_args()
    if not args.check_key and not (args.word and args.word.strip()):
        parser.error("请提供一个英文候选词；中文或描述先由 Agent 转换。")
    try:
        if args.word and re.search(r"[\u3400-\u9fff\U00020000-\U000323af]", args.word):
            raise LookupFailure("中文输入请先由 Agent 翻译或提炼为英文候选，再调用此脚本。")
        key, source = load_key()
        if args.check_key:
            print(json.dumps({"configured": True, "source": source}))
            return 0
        word = args.word.strip()
        data = fetch_response(word, key)
        if args.format == "raw":
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            result = parse_response(data, word, all_relations=args.all_relations)
            print(json.dumps(result, ensure_ascii=False, indent=2)
                  if args.format == "json" else render_markdown(result), end="\n" if args.format == "json" else "")
        return 0
    except LookupFailure as error:
        print(f"查词失败：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
