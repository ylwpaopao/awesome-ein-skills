"""Canonical vocabulary data; no filesystem mutation or service calls."""
import copy
import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_LIBRARY = Path.home() / ".config/dictation-dictionary/vocabulary.json"
DEFAULT_STATE = Path.home() / ".local/state/dictation-dictionary"
FIELDS = {"id", "term", "misheard_as", "domains", "sources", "enabled"}


def word(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("words must be nonempty strings without surrounding whitespace")
    if any(ord(c) < 32 or 127 <= ord(c) < 160 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError("control characters and invalid Unicode are not allowed")
    return value


def words(values):
    if not isinstance(values, list):
        raise ValueError("word list must be an array")
    return list(dict.fromkeys(word(v) for v in values))


def _sources(values):
    if not isinstance(values, list):
        raise ValueError("sources must be an array")
    result = []
    for source in values:
        if not isinstance(source, dict) or set(source) - {"url", "locator", "timestamp"}:
            raise ValueError("sources contain only url, locator and timestamp")
        url = urlsplit(word(source.get("url")))
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("source URL must be an HTTP(S) link without credentials")
        for value in source.values():
            word(value)
        if source not in result:
            result.append(copy.deepcopy(source))
    return result


def validate_library(value):
    if not isinstance(value, dict) or set(value) != {"version", "entries"}:
        raise ValueError("library must contain version and entries only")
    if type(value["version"]) is not int or value["version"] != 1 or not isinstance(value["entries"], list):
        raise ValueError("unsupported library version or entries")
    result, ids, terms = [], set(), set()
    for item in value["entries"]:
        if not isinstance(item, dict) or set(item) != FIELDS:
            raise ValueError("entry fields must be id, term, misheard_as, domains, sources, enabled")
        ident, term = word(item["id"]), word(item["term"])
        if ident in ids or term in terms or type(item["enabled"]) is not bool:
            raise ValueError("duplicate id/term or invalid enabled state")
        ids.add(ident)
        terms.add(term)
        result.append({"id": ident, "term": term, "misheard_as": words(item["misheard_as"]),
                       "domains": words(item["domains"]), "sources": _sources(item["sources"]),
                       "enabled": item["enabled"]})
    return {"version": 1, "entries": result}


def load_library(path=DEFAULT_LIBRARY):
    return validate_library(json.loads(Path(path).read_text(encoding="utf-8")))


def library_bytes(value):
    return (json.dumps(validate_library(value), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def merge_entries(base, incoming):
    result = validate_library(base)
    if not isinstance(incoming, list):
        raise ValueError("candidates must be an array")
    by_term = {v["term"]: v for v in result["entries"]}
    for candidate in incoming:
        if not isinstance(candidate, dict) or "term" not in candidate or set(candidate) - FIELDS:
            raise ValueError("invalid candidate fields")
        term = word(candidate["term"])
        defaults = {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, "dictation-dictionary:" + term)),
                    "term": term, "misheard_as": [], "domains": [], "sources": [], "enabled": True}
        defaults.update(copy.deepcopy(candidate))
        new = validate_library({"version": 1, "entries": [defaults]})["entries"][0]
        if term in by_term:
            old = by_term[term]
            for field in ("misheard_as", "domains", "sources"):
                for item in new[field]:
                    if item not in old[field]:
                        old[field].append(item)
            if "enabled" in candidate:
                old["enabled"] = new["enabled"]
        else:
            result["entries"].append(new)
            by_term[term] = new
    return validate_library(result)


def active_words(library):
    return [v["term"] for v in validate_library(library)["entries"] if v["enabled"]]


def diff_words(before, after):
    before, after = words(before), words(after)
    return {"added": [w for w in after if w not in before],
            "removed": [w for w in before if w not in after],
            "unchanged": [w for w in before if w in after]}


def additive_words(before, desired):
    return words(before + [w for w in words(desired) if w not in before])
