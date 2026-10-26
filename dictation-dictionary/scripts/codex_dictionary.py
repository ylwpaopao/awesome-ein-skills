"""Edit one TOML array while preserving every byte outside its value."""
import copy
import json
import re
import tomllib

from vocabulary import word


def _parsed(data):
    try:
        return tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("config is not valid UTF-8 TOML") from exc


def read_codex(data):
    try:
        value = _parsed(data)["desktop"]["dictationDictionary"]
    except (KeyError, TypeError) as exc:
        raise ValueError("desktop.dictationDictionary is missing") from exc
    if not isinstance(value, list):
        raise ValueError("desktop.dictationDictionary must be a string array")
    return [word(v) for v in value]


def _mask(text):
    """Hide strings/comments but retain offsets, newlines and syntax."""
    masked, pos = list(text), 0
    while pos < len(text):
        start = pos
        if text[pos] == "#":
            end = text.find("\n", pos)
            pos = len(text) if end < 0 else end
        elif text[pos] in "\"'":
            quote = text[pos]
            triple = text.startswith(quote * 3, pos)
            pos += 3 if triple else 1
            while pos < len(text):
                if quote == '"' and text[pos] == "\\":
                    pos += 2
                elif triple and text.startswith(quote * 3, pos):
                    pos += 3
                    # TOML permits one or two quotes immediately before the delimiter.
                    for _ in range(2):
                        if pos < len(text) and text[pos] == quote:
                            pos += 1
                    break
                elif not triple and text[pos] == quote:
                    pos += 1
                    break
                else:
                    pos += 1
        else:
            pos += 1
            continue
        for i in range(start, min(pos, len(text))):
            if text[i] not in "\r\n":
                masked[i] = " "
    return "".join(masked)


def _span(text):
    masked = _mask(text)
    headers = list(re.finditer(r"(?m)^[ \t]*\[([^\r\n]+)\][ \t]*\r?$", masked))
    desktop = [i for i, h in enumerate(headers) if h.group(1).strip() == "desktop"]
    if len(desktop) != 1:
        raise ValueError("cannot safely locate a unique [desktop] table")
    index = desktop[0]
    begin = headers[index].end()
    end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
    keys = list(re.finditer(r"(?m)^[ \t]*dictationDictionary[ \t]*=[ \t]*(\[)", masked[begin:end]))
    if len(keys) != 1:
        raise ValueError("cannot safely locate the dictionary array; unsupported layout")
    start = begin + keys[0].start(1)
    depth = 0
    for pos in range(start, len(masked)):
        if masked[pos] == "[":
            depth += 1
        elif masked[pos] == "]":
            depth -= 1
            if depth == 0:
                return start, pos + 1
    raise ValueError("dictionary array is not closed")


def patch_codex(data, desired):
    read_codex(data)
    if not isinstance(desired, list):
        raise ValueError("dictionary must be an array")
    desired = [word(v) for v in desired]
    text = data.decode("utf-8")
    start, end = _span(text)
    prefix, suffix = text[:start].encode("utf-8"), text[end:].encode("utf-8")
    replacement = json.dumps(desired, ensure_ascii=False).encode("utf-8")
    after = prefix + replacement + suffix
    expected = copy.deepcopy(_parsed(data))
    expected["desktop"]["dictationDictionary"] = desired
    if _parsed(after) != expected or read_codex(after) != desired:
        raise ValueError("patch would change something other than the dictionary")
    if after[:len(prefix)] != data[:len(prefix)] or (suffix and not after.endswith(suffix)):
        raise ValueError("bytes outside dictionary changed")
    return after
