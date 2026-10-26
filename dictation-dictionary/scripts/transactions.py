"""Review-bound plans, local backups and guarded file writes."""
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
import stat
import tempfile
import uuid
from pathlib import Path

from codex_dictionary import patch_codex, read_codex
from vocabulary import active_words, diff_words, library_bytes, validate_library, words

TARGETS = {"library", "codex", "typeless", "plaud-cn", "git"}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def make_plan(target, before, after):
    if target not in TARGETS or not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("invalid plan target/state")
    result = {"version": 1, "target": target, "before": copy.deepcopy(before), "after": copy.deepcopy(after)}
    if "words" in before and "words" in after:
        result["diff"] = diff_words(before["words"], after["words"])
    return result


def plan_id(plan):
    if plan.get("version") != 1 or plan.get("target") not in TARGETS:
        raise ValueError("invalid plan")
    return sha(json_bytes(plan))


def require_approval(plan, approval):
    if not approval or approval != plan_id(plan):
        raise ValueError("explicit approval must match this exact preview's plan id")


def save_plan(path, plan):
    document = {"id": plan_id(plan), "plan": plan}
    save_json(path, document)
    return document


def load_plan(path):
    document = json.loads(Path(path).read_bytes())
    if not isinstance(document, dict) or set(document) != {"id", "plan"}:
        raise ValueError("invalid plan document")
    if not isinstance(document["plan"], dict) or document["id"] != plan_id(document["plan"]):
        raise ValueError("plan document changed")
    return document["plan"]


def secure_dir(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("state directory must not be a symbolic link")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.chmod(0o700)
    return path


def save_json(path, value):
    path = Path(path)
    secure_dir(path.parent)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())
    return path


def backup_bytes(root, target, data, mode):
    if target not in TARGETS:
        raise ValueError("invalid backup target")
    root = secure_dir(root)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    suffix = ".toml" if target == "codex" else ".json"
    path = root / (stamp + "-" + target + "-" + uuid.uuid4().hex[:8] + suffix)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if sha(path.read_bytes()) != sha(data):
        raise OSError("backup verification failed")
    return path


def file_snapshot(path):
    path = Path(path).expanduser().absolute()
    if path.is_symlink():
        raise ValueError("target must not be a symbolic link")
    if not path.exists():
        return {"path": str(path), "exists": False, "sha256": None, "mode": None}, None
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("target must be a regular file owned by the current user")
    data = path.read_bytes()
    return {"path": str(path), "exists": True, "sha256": sha(data),
            "mode": stat.S_IMODE(info.st_mode)}, data


def plan_codex(path, desired, replace=False):
    before, data = file_snapshot(path)
    if data is None:
        raise ValueError("Codex config does not exist; it will not be created")
    before["words"] = read_codex(data)
    desired = words(desired)
    after = desired if replace else before["words"] + [w for w in desired if w not in before["words"]]
    patch_codex(data, after)  # Refuse unsupported syntax while planning, before any write.
    return make_plan("codex", before, {"words": after})


def plan_restore_codex(path, backup):
    return plan_codex(path, read_codex(Path(backup).read_bytes()), replace=True)


def plan_library(path, desired):
    desired = validate_library(desired)
    before, data = file_snapshot(path)
    current = validate_library(json.loads(data)) if data is not None else None
    before.update({"library": current, "words": active_words(current) if current else []})
    return make_plan("library", before, {"library": desired, "words": active_words(desired)})


def _check_current(before):
    actual, data = file_snapshot(before["path"])
    if any(actual[k] != before[k] for k in ("exists", "sha256", "mode")):
        raise ValueError("target changed since preview; create a new plan and ask again")
    return data


def _atomic_write(path, data, mode, before):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".dictation-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _check_current(before)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def apply_file_plan(plan, approval, state):
    require_approval(plan, approval)
    if plan["target"] not in {"library", "codex"}:
        raise ValueError("this plan requires a different transport")
    state = secure_dir(state)
    locks = secure_dir(state / "locks")
    ident = plan_id(plan)
    receipt_path = state / "receipts" / (ident + ".json")
    before = plan["before"]
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(locks / sha(before["path"].encode()), flags, 0o600), "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_bytes())
            current, _ = file_snapshot(before["path"])
            if receipt["after_sha256"] == current["sha256"]:
                return dict(receipt, status="already_applied")
        data = _check_current(before)
        if plan["target"] == "codex":
            new = data if read_codex(data) == plan["after"]["words"] else patch_codex(data, plan["after"]["words"])
        else:
            desired = validate_library(plan["after"]["library"])
            new = data if data is not None and validate_library(json.loads(data)) == desired else library_bytes(desired)
        if new == data:
            return {"status": "unchanged", "plan_id": ident, "target": plan["target"]}
        backup = backup_bytes(state / "backups", plan["target"],
                              data if data is not None else json_bytes({"existed": False}), before["mode"])
        _atomic_write(before["path"], new, before["mode"] if data is not None else 0o600, before)
        if Path(before["path"]).read_bytes() != new:
            raise OSError("read-back verification failed; backup: " + str(backup))
        receipt = {"status": "applied", "plan_id": ident, "target": plan["target"],
                   "backup": str(backup), "backup_sha256": sha(backup.read_bytes()),
                   "path": before["path"], "after_sha256": sha(new), "existed_before": data is not None}
        try:
            save_json(receipt_path, receipt)
        except OSError as exc:
            raise OSError("target written but receipt failed; backup: " + str(backup)) from exc
        return receipt
