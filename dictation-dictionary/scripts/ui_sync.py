"""Review and backup receipts for UI transports; never drives the UI itself."""
import datetime as dt
import copy
import json
from pathlib import Path

import transactions as tx
from vocabulary import additive_words, words


def inventory(value):
    if not isinstance(value, dict) or set(value) != {"target", "words", "complete", "evidence"}:
        raise ValueError("inventory must contain only extracted words and completeness evidence")
    if value["target"] not in {"typeless", "plaud-cn"} or value["complete"] is not True:
        raise ValueError("incomplete or unsupported inventory")
    terms = words(value["words"])
    if len(terms) != len(value["words"]):
        raise ValueError("duplicate inventory terms; inspect the actual list")
    proof = value["evidence"]
    allowed = {"kind", "count", "at_end", "identity", "observed_at", "all_terms", "enabled"}
    if not isinstance(proof, dict) or set(proof) - allowed:
        raise ValueError("invalid inventory evidence")
    if proof.get("all_terms") is not True or proof.get("enabled") is not True:
        raise ValueError("inventory must be unfiltered and enabled")
    if not isinstance(proof.get("identity"), str) or not proof["identity"].strip():
        raise ValueError("observed account identity is required")
    try:
        observed = dt.datetime.fromisoformat(proof.get("observed_at", "").replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError("observation needs a timezone")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("invalid observation timestamp") from exc
    if proof.get("kind") == "count":
        if type(proof.get("count")) is not int or proof["count"] != len(terms):
            raise ValueError("displayed count does not match extracted terms")
    elif proof.get("kind") != "end" or proof.get("at_end") is not True:
        raise ValueError("a displayed count or observed list end is required")
    return {"target": value["target"], "words": terms, "complete": True, "evidence": dict(proof)}


def _same(before, current):
    if (before["target"] != current["target"]
            or before["evidence"]["identity"] != current["evidence"]["identity"]
            or set(before["words"]) != set(current["words"])):
        raise ValueError("live account or dictionary changed; create a new preview")


def plan_ui(current, desired):
    current = inventory(current)
    return tx.make_plan(current["target"], current,
                        {"words": additive_words(current["words"], words(desired))})


def prepare_ui(plan, approval, current, state):
    tx.require_approval(plan, approval)
    before, current = inventory(plan["before"]), inventory(current)
    if plan["target"] != before["target"]:
        raise ValueError("plan target mismatch")
    _same(before, current)
    after = words(plan["after"]["words"])
    if not set(before["words"]) <= set(after):
        raise ValueError("UI automatic synchronization supports additions only")
    added = [term for term in after if term not in before["words"]]
    backup = tx.backup_bytes(Path(state) / "backups", plan["target"], tx.json_bytes(current), 0o600)
    return {"status": "ready", "target": plan["target"], "plan_id": tx.plan_id(plan),
            "plan": copy.deepcopy(plan),
            "backup": str(backup.absolute()), "backup_sha256": tx.sha(backup.read_bytes()),
            "before": current, "after": {"words": after}, "added": added}


def check_ready(ready, state):
    if ready.get("status") != "ready" or ready.get("target") not in {"typeless", "plaud-cn"}:
        raise ValueError("a prepared UI receipt is required")
    plan = ready.get("plan")
    if not isinstance(plan, dict):
        raise ValueError("receipt requires its original approved plan")
    tx.require_approval(plan, ready.get("plan_id"))
    original = inventory(plan["before"])
    prepared = inventory(ready["before"])
    _same(original, prepared)
    after = words(plan["after"]["words"])
    added = [term for term in after if term not in original["words"]]
    if (ready["target"] != plan["target"] or original["target"] != plan["target"]
            or not set(original["words"]) <= set(after)
            or ready["after"] != plan["after"] or ready["added"] != added):
        raise ValueError("receipt actions differ from the approved plan")
    backup = Path(ready["backup"])
    if (backup.is_symlink() or backup.resolve().parent != (Path(state) / "backups").resolve()
            or tx.sha(backup.read_bytes()) != ready["backup_sha256"]):
        raise ValueError("backup is missing, changed, or outside this state directory")
    _same(inventory(json.loads(backup.read_bytes())), prepared)
    return ready


def verify_ui(ready, current, state):
    check_ready(ready, state)
    backup = Path(ready["backup"])
    before, current = inventory(ready["before"]), inventory(current)
    if (current["target"] != before["target"] or ready["target"] != before["target"]
            or current["evidence"]["identity"] != before["evidence"]["identity"]
            or set(current["words"]) != set(words(ready["after"]["words"]))):
        raise ValueError("read-back differs from the approved dictionary")
    result = {"status": "verified", "target": ready["target"], "plan_id": ready["plan_id"],
              "backup": str(backup), "backup_sha256": ready["backup_sha256"], "current": current}
    ident = ready["plan_id"]
    if not isinstance(ident, str) or len(ident) != 64 or any(c not in "0123456789abcdef" for c in ident):
        raise ValueError("invalid plan id")
    receipt = Path(state) / "receipts" / (ident + "-ui.json")
    if receipt.exists():
        prior = json.loads(receipt.read_bytes())
        _same(inventory(prior["current"]), current)
        return dict(prior, status="already_verified")
    tx.save_json(receipt, result)
    return result
