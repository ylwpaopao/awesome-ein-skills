"""A dedicated, vocabulary-only Git store. Fetch never updates the worktree."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import transactions as tx
from vocabulary import active_words, merge_entries, validate_library


def _git(repo, *args, raw=False, optional=False):
    command = ["git"]
    if shutil.which("gh"):
        command += ["-c", "credential.helper=!gh auth git-credential"]
    command += ["-C", str(repo), *args]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=dict(os.environ, GIT_TERMINAL_PROMPT="0"), timeout=40)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Git operation timed out") from exc
    if result.returncode:
        if optional:
            return None
        raise ValueError("Git failed: " + result.stderr.decode(errors="replace")[:800])
    return result.stdout if raw else result.stdout.decode().strip()


def _github_private(name):
    if not shutil.which("gh"):
        raise ValueError("gh is required to verify GitHub repository privacy; no data was pushed")
    result = subprocess.run(["gh", "repo", "view", name, "--json", "isPrivate", "--jq", ".isPrivate"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if result.returncode:
        raise ValueError("could not verify private GitHub repository with existing login")
    return result.stdout.strip() == b"true"


def _verify_remote(remote, check_privacy=True):
    # Local repositories support isolated tests and local-only backups.
    if Path(remote).is_absolute() and Path(remote).is_dir():
        return
    match = re.fullmatch(r"git@github\.com:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", remote)
    if match:
        name = match.group(1)
    else:
        url = urlsplit(remote)
        if url.scheme != "https" or url.hostname != "github.com" or url.username or url.password:
            raise ValueError("use a private GitHub HTTPS/SSH URL without embedded credentials")
        name = url.path.strip("/")
        if url.query or url.fragment or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
            raise ValueError("invalid GitHub repository URL")
    name = name[:-4] if name.endswith(".git") else name
    if check_privacy and not _github_private(name):
        raise ValueError("repository must be private")


def initialize_store(repo, remote):
    _verify_remote(remote)
    repo = Path(repo).expanduser().absolute()
    if repo.exists() and any(repo.iterdir()):
        raise ValueError("store initialization requires an empty directory")
    repo.mkdir(parents=True, mode=0o700, exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "remote", "add", "origin", remote)
    return inspect_store(repo)


def inspect_store(repo):
    repo = Path(repo).expanduser().resolve()
    if Path(_git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise ValueError("store must be the root of its own Git repository")
    tracked = _git(repo, "ls-files", "-z", raw=True).split(b"\0")
    if any(name and name != b"vocabulary.json" for name in tracked):
        raise ValueError("store may track vocabulary.json only")
    if _git(repo, "diff", "--cached", "--name-only"):
        raise ValueError("store has staged changes; review them separately")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all", raw=True).decode()
    if any(line[3:] != "vocabulary.json" for line in status.splitlines()):
        raise ValueError("store contains unrelated working files")
    branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", optional=True)
    if not branch:
        raise ValueError("detached vocabulary store is unsupported")
    remote = _git(repo, "remote", "get-url", "origin")
    _verify_remote(remote, check_privacy=False)
    push_urls = _git(repo, "remote", "get-url", "--push", "--all", "origin").splitlines()
    if push_urls != [remote]:
        raise ValueError("push must have exactly one destination matching the reviewed origin URL")
    return {"repo": str(repo), "branch": branch,
            "head": _git(repo, "rev-parse", "--verify", "HEAD", optional=True),
            "remote": remote, "push_urls": push_urls, "status": status}


def _remote_oid(repo, branch):
    output = _git(repo, "ls-remote", "--heads", "origin", "refs/heads/" + branch)
    return output.split()[0] if output else None


def _at_commit(repo, oid):
    names = _git(repo, "ls-tree", "-r", "--name-only", oid).splitlines()
    if names != ["vocabulary.json"]:
        raise ValueError("remote/history must contain vocabulary.json only")
    raw = _git(repo, "show", oid + ":vocabulary.json", raw=True)
    library = validate_library(json.loads(raw))
    return {"oid": oid, "library": library, "content": raw.decode("utf-8"), "sha256": tx.sha(raw)}


def fetch_remote_library(repo):
    info = inspect_store(repo)
    _verify_remote(info["remote"])
    if not _remote_oid(repo, info["branch"]):
        return {"oid": None, "library": None, "content": None, "sha256": None}
    _git(repo, "fetch", "--no-tags", "origin", "refs/heads/" + info["branch"])
    return _at_commit(repo, _git(repo, "rev-parse", "FETCH_HEAD"))


def _ancestor(repo, old, new):
    return _git(repo, "merge-base", "--is-ancestor", old, new, optional=True) is not None


def plan_store_update(repo, desired):
    desired = validate_library(desired)
    info = inspect_store(repo)
    remote = fetch_remote_library(repo)
    local_plan = tx.plan_library(Path(repo) / "vocabulary.json", desired)
    local = local_plan["before"]["library"]
    if local and not {e["term"] for e in local["entries"]} <= {e["term"] for e in desired["entries"]}:
        raise ValueError("default Git sync preserves entries; use enabled=false for retired terms")
    head, remote_head = info["head"], remote["oid"]
    if head and remote_head and not (_ancestor(repo, head, remote_head) or _ancestor(repo, remote_head, head)):
        raise ValueError("store history diverged; resolve explicitly without force pushing")
    if remote_head and remote_head != head and (not head or _ancestor(repo, head, remote_head)):
        base = _at_commit(repo, head)["library"] if head else {"version": 1, "entries": []}
        previous = {e["term"]: e for e in base["entries"]}
        changes = [e for e in desired["entries"] if previous.get(e["term"]) != e]
        merged = remote["library"]
        remote_terms = {e["term"] for e in merged["entries"]}
        # Preserve local entries without overwriting newer remote metadata with stale copies.
        missing = [e for e in desired["entries"] if e["term"] not in remote_terms]
        desired = merge_entries(merged, missing + changes)
    before = dict(info, remote_state=remote, file=local_plan["before"],
                  words=active_words(local) if local else [])
    after = {"library": desired, "words": active_words(desired)}
    plan = tx.make_plan("git", before, after)
    plan["remote_diff"] = tx.diff_words(active_words(remote["library"]) if remote_head else [], after["words"])
    return plan


def apply_store_update(plan, approval, state):
    tx.require_approval(plan, approval)
    if plan["target"] != "git":
        raise ValueError("expected Git plan")
    before, after = plan["before"], plan["after"]
    repo = Path(before["repo"])
    current = inspect_store(repo)
    if any(current[k] != before[k] for k in ("repo", "head", "branch", "remote", "push_urls", "status")):
        raise ValueError("local Git state changed since preview")
    tx._check_current(before["file"])
    remote = fetch_remote_library(repo)
    if remote != before["remote_state"]:
        raise ValueError("remote changed since preview; ask for a new approval")
    if (before["head"] == remote["oid"] and not before["status"]
            and before["file"]["library"] == after["library"] == remote["library"]):
        return {"status": "unchanged", "target": "git", "plan_id": tx.plan_id(plan), "repo": str(repo)}
    state = tx.secure_dir(state)
    remote_backup = tx.backup_bytes(state / "backups", "git",
                                   remote["content"].encode() if remote["oid"] else tx.json_bytes({"existed": False}), 0o600)
    head, remote_head = before["head"], remote["oid"]
    if remote_head and remote_head != head and (not head or _ancestor(repo, head, remote_head)):
        # Align Git metadata without an implicit checkout overwriting the reviewed file.
        _git(repo, "read-tree", remote_head)
        _git(repo, "update-ref", "refs/heads/" + before["branch"], remote_head, head or "0" * 40)
    inner = tx.make_plan("library", before["file"], {"library": after["library"], "words": after["words"]})
    local = tx.apply_file_plan(inner, tx.plan_id(inner), state)
    result = {"target": "git", "plan_id": tx.plan_id(plan), "local": local,
              "remote_backup": str(remote_backup), "repo": str(repo)}
    try:
        _git(repo, "add", "--", "vocabulary.json")
        staged = _git(repo, "diff", "--cached", "--name-only").splitlines()
        if any(name != "vocabulary.json" for name in staged):
            raise ValueError("unexpected staged files; refusing commit")
        if staged:
            _git(repo, "commit", "--only", "-m", "Update reviewed dictation vocabulary", "--", "vocabulary.json")
        head = _git(repo, "rev-parse", "HEAD")
        result["commit"] = head
        _verify_remote(before["remote"])
        if _remote_oid(repo, before["branch"]) != remote_head:
            raise ValueError("remote advanced before push")
        push_urls = _git(repo, "remote", "get-url", "--push", "--all", "origin").splitlines()
        if (_git(repo, "remote", "get-url", "origin") != before["remote"]
                or push_urls != before["push_urls"] or push_urls != [before["remote"]]):
            raise ValueError("push destination changed since preview")
        # Preserve origin's resolved push semantics; passing a raw URL can reapply pushInsteadOf.
        _git(repo, "push", "origin", "HEAD:refs/heads/" + before["branch"])
        if _remote_oid(repo, before["branch"]) != head:
            raise ValueError("remote changed after push; refresh its state")
        result["status"] = "pushed"
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        result.update(status="push_failed", error=str(exc))
    tx.save_json(state / "receipts" / (tx.plan_id(plan) + ".json"), result)
    return result
