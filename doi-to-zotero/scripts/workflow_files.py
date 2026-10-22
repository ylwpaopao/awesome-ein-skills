# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""Track task downloads and remove them only after a verified Zotero copy exists."""

import argparse
import hashlib
import json
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


DOMAIN_REGISTRY = Path(__file__).parents[1] / "references" / "scihub-domains.json"
DOMAIN_RESULTS = {"user-reported", "available", "network-unavailable", "policy-blocked"}


def domain_url(value):
    url = urlsplit(value)
    host = url.hostname or ""
    labels = host.split(".")
    if (
        url.scheme != "https" or url.username or url.password or url.port
        or url.path not in {"", "/"} or url.query or url.fragment or len(labels) < 2
        or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
    ):
        raise ValueError("Expected an HTTPS domain root without credentials, port or query")
    return f"https://{host}/"


def read_domains(registry=DOMAIN_REGISTRY):
    registry = Path(registry)
    if registry.is_symlink():
        raise ValueError("Domain registry must not be a symlink")
    state = json.loads(registry.read_text())
    if state.get("schema_version") != 1 or not isinstance(state.get("domains"), list):
        raise ValueError("Invalid domain registry")
    seen = set()
    for entry in state["domains"]:
        url = domain_url(entry["url"])
        if url in seen or entry.get("last_result") not in DOMAIN_RESULTS:
            raise ValueError("Duplicate domain or invalid observation status")
        seen.add(url)
    return state


def record_domain(value, result, *, registry=DOMAIN_REGISTRY):
    if result not in DOMAIN_RESULTS - {"user-reported"}:
        raise ValueError("Record an actual available, network-unavailable or policy-blocked observation")
    url = domain_url(value)
    state = read_domains(registry)
    entry = next((item for item in state["domains"] if domain_url(item["url"]) == url), None)
    if entry is None:
        entry = {"url": url, "last_verified_at": None}
        state["domains"].append(entry)
    observed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry.update(last_result=result, last_observed_at=observed)
    if result == "available":
        entry["last_verified_at"] = observed
    Path(registry).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    return entry


def normalize_doi(value):
    value = value.strip()
    if value.lower().startswith(("http://", "https://")):
        url = urlsplit(value)
        if url.hostname not in {"doi.org", "dx.doi.org", "www.doi.org"}:
            raise ValueError("Only doi.org URLs or bare DOIs are accepted")
        value = unquote(url.path.lstrip("/"))
    else:
        value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    if not re.fullmatch(r"10\.\d{4,9}/\S+", value, flags=re.ASCII):
        raise ValueError("Invalid DOI")
    return value


def resolve_primary_doi(page):
    if page.get("primary_doi"):
        doi = normalize_doi(page["primary_doi"])
        return {"doi": doi, "title": page.get("title"), "url": page.get("url")}
    candidates = {}
    for metadata in page.get("metadata", []):
        name = str(metadata.get("name", "")).lower()
        if name not in {"citation_doi", "prism.doi", "dc.identifier", "dc.identifier.doi"}:
            continue
        try:
            doi = normalize_doi(str(metadata.get("content", "")))
        except ValueError:
            continue
        candidates[doi.lower()] = doi
    if len(candidates) != 1:
        message = "Conflicting primary DOI metadata" if candidates else "No primary article DOI found"
        raise ValueError(message)
    return {"doi": next(iter(candidates.values())), "title": page.get("title"), "url": page.get("url")}


def path_key(path):
    return hashlib.sha256(str(path.absolute()).encode()).hexdigest()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pdf_info(path):
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("Expected an absolute path to a regular file, not a symlink")
    with path.open("rb") as stream:
        if not stream.read(8).startswith(b"%PDF-"):
            raise ValueError("File has no PDF signature; it may be HTML or an error page")
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "sha256": digest(path),
    }


def save(session, state):
    session.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def prepare(doi, *, downloads=None, parent=None):
    doi = normalize_doi(doi)
    started_ns = time.time_ns()
    downloads = (downloads or Path.home() / "Downloads").resolve()
    directory = Path(tempfile.mkdtemp(prefix="doi-to-zotero-", dir=parent)).resolve()
    session = directory / "session.json"
    state = {
        "doi": doi,
        "started_ns": started_ns,
        "directory": str(directory),
        "downloads": str(downloads),
        "preexisting": [path_key(p) for p in downloads.iterdir()] if downloads.is_dir() else [],
    }
    save(session, state)
    return {"doi": doi, "session": str(session), "download_directory": str(directory)}


def load(session):
    session = Path(session).absolute()
    if session.is_symlink() or session.name != "session.json":
        raise ValueError("Expected the session.json returned by prepare")
    state = json.loads(session.read_text())
    if session.parent.resolve() != Path(state["directory"]).resolve():
        raise ValueError("Session directory mismatch")
    return session, state


def register(session, source, *, cache_source=None):
    session, state = load(session)
    if state.get("source"):
        raise ValueError("A PDF is already registered for this session")
    source = Path(source)
    info = pdf_info(source)
    actual = Path(info["path"])
    if actual.parent == Path(state["downloads"]):
        if path_key(actual) in state["preexisting"]:
            raise ValueError("File existed in Downloads before this task; leave it unchanged")
    elif not actual.is_relative_to(Path(state["directory"])):
        raise ValueError("Download must be in this task directory or Downloads")
    if cache_source is not None:
        cache_path = Path(cache_source)
        cache = pdf_info(cache_path)
        cache_actual = Path(cache["path"])
        if cache_actual.samefile(actual):
            raise ValueError("Cache origin must be a separate file")
        in_temp = cache_actual.is_relative_to(Path(tempfile.gettempdir()).resolve())
        in_user_cache = cache_actual.is_relative_to(Path.home() / ".cache") or (
            cache_actual.is_relative_to(Path.home() / "Library")
            and any(p.name == "Caches" for p in cache_actual.parents)
        )
        if not (in_temp or in_user_cache):
            raise ValueError("Cache origin must be in a temporary or user cache directory")
        stat = cache_actual.stat()
        born_ns = getattr(stat, "st_birthtime_ns", None)
        if born_ns is None:
            born_ns = int(stat.st_birthtime * 1_000_000_000) if hasattr(stat, "st_birthtime") else stat.st_ctime_ns
        if "started_ns" not in state or born_ns < state["started_ns"]:
            raise ValueError("Cache file predates this task; leave it unchanged")
        if cache["sha256"] != info["sha256"]:
            raise ValueError("Cache origin does not match the staged PDF")
        state["cache_source"] = cache
    state["source"] = info
    save(session, state)
    return {"doi": state["doi"], "source": info["path"], "sha256": info["sha256"]}


def finish(session, stored, *, reader_verified=False):
    if not reader_verified:
        raise ValueError("First open the Zotero attachment and verify its readable first page")
    session, state = load(session)
    if not state.get("source"):
        raise ValueError("No task download is registered")
    source = Path(state["source"]["path"])
    if pdf_info(source) != state["source"]:
        raise ValueError("Source file changed since registration; leave it unchanged")
    stored = Path(stored)
    copy = pdf_info(stored)
    actual = Path(copy["path"])
    if actual.parent.parent.name != "storage" or not re.fullmatch(r"[A-Z0-9]{8}", actual.parent.name):
        raise ValueError("Expected a Zotero-managed storage/ITEMKEY/file.pdf copy")
    if source.samefile(actual):
        raise ValueError("Attachment is the download itself, not an independent copy")
    if copy["sha256"] != state["source"]["sha256"]:
        raise ValueError("Zotero copy does not match the downloaded PDF")
    cache_source = None
    if state.get("cache_source"):
        cache_source = Path(state["cache_source"]["path"])
        if pdf_info(cache_source) != state["cache_source"]:
            raise ValueError("Cache file changed since registration; leave downloads unchanged")
        if cache_source.samefile(actual):
            raise ValueError("Zotero copy is not independent of the cache origin")
        cache_source.unlink()
    source.unlink()
    session.unlink()
    directory = session.parent
    if not any(directory.iterdir()):
        directory.rmdir()
    result = {"doi": state["doi"], "stored": str(actual), "deleted_download": str(source)}
    if cache_source is not None:
        result["deleted_cache"] = str(cache_source)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("domains", help="Read observed Sci-Hub domains in recorded order; no network probing")
    observation = sub.add_parser("record-domain", help="Record a browser observation, not an availability guess")
    observation.add_argument("url")
    observation.add_argument("result", choices=sorted(DOMAIN_RESULTS - {"user-reported"}))
    resolve = sub.add_parser("resolve", help="Resolve primary DOI from observed article metadata JSON")
    resolve.add_argument("evidence")
    check = sub.add_parser("check", help="Check a candidate's PDF signature before reading its first page")
    check.add_argument("source")
    new = sub.add_parser("prepare")
    new.add_argument("doi")
    record = sub.add_parser("register")
    record.add_argument("session")
    record.add_argument("source")
    record.add_argument("--cache-origin", help="Exact task-created cache file returned by the download tool")
    cleanup = sub.add_parser("finish")
    cleanup.add_argument("session")
    cleanup.add_argument("stored")
    cleanup.add_argument("--reader-verified", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "domains":
            result = read_domains()
        elif args.command == "record-domain":
            result = record_domain(args.url, args.result)
        elif args.command == "resolve":
            result = resolve_primary_doi(json.loads(Path(args.evidence).read_text()))
        elif args.command == "check":
            result = pdf_info(Path(args.source))
        elif args.command == "prepare":
            result = prepare(args.doi)
        elif args.command == "register":
            result = register(args.session, args.source, cache_source=args.cache_origin)
        else:
            result = finish(args.session, args.stored, reader_verified=args.reader_verified)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
