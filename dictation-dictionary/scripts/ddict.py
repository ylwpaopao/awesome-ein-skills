"""Run with uv run python scripts/ddict.py --help."""
import argparse
import csv
import json
import sys
from pathlib import Path

from vocabulary import DEFAULT_LIBRARY, DEFAULT_STATE, active_words, diff_words, load_library, merge_entries
import transactions as tx

DEFAULT_CONFIG = Path.home() / ".codex/config.toml"


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parser():
    root = argparse.ArgumentParser(description="听写词库：预览、确认、备份后同步。默认命令只读。")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("validate", "export"):
        sub = commands.add_parser(name)
        sub.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
        if name == "export":
            sub.add_argument("--format", choices=["json", "csv"], default="json")
    sub = commands.add_parser("diff")
    sub.add_argument("--before", type=Path, required=True, help="JSON string array")
    sub.add_argument("--after", type=Path, required=True, help="JSON string array")
    for name in ("codex-plan", "restore-codex-plan"):
        sub = commands.add_parser(name, help="只生成预览，不改配置")
        sub.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        sub.add_argument("--out", type=Path, required=True)
        if name == "codex-plan":
            sub.add_argument("--words", type=Path, required=True, help="JSON string array")
            sub.add_argument("--replace", action="store_true", help="预览明确的替换/删除，默认仅增补")
        else:
            sub.add_argument("--backup", type=Path, required=True)
    sub = commands.add_parser("library-plan", help="只生成主词库变更预览")
    sub.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    group = sub.add_mutually_exclusive_group(required=True)
    group.add_argument("--candidates", type=Path, help="JSON candidate array")
    group.add_argument("--desired", type=Path, help="完整目标词库，用于明确的替换或恢复")
    sub.add_argument("--out", type=Path, required=True)
    sub = commands.add_parser("preview")
    sub.add_argument("--plan", type=Path, required=True)
    sub = commands.add_parser("apply", help="收到用户对具体预览的确认后才传 --approve")
    sub.add_argument("--plan", type=Path, required=True)
    sub.add_argument("--approve", default="", help="用户已确认的完整 plan id")
    sub.add_argument("--state", type=Path, default=DEFAULT_STATE)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "validate":
            value = load_library(args.library)
            output({"valid": True, "entries": len(value["entries"])})
        elif args.command == "export":
            value = active_words(load_library(args.library))
            if args.format == "csv":
                writer = csv.writer(sys.stdout, lineterminator="\n")
                writer.writerows([[v] for v in value])
            else:
                output(value)
        elif args.command == "diff":
            output(diff_words(json.loads(args.before.read_text()), json.loads(args.after.read_text())))
        elif args.command == "codex-plan":
            plan = tx.plan_codex(args.config, json.loads(args.words.read_bytes()), args.replace)
            output(tx.save_plan(args.out, plan))
        elif args.command == "restore-codex-plan":
            output(tx.save_plan(args.out, tx.plan_restore_codex(args.config, args.backup)))
        elif args.command == "library-plan":
            if args.desired:
                desired = load_library(args.desired)
            else:
                base = load_library(args.library) if args.library.exists() else {"version": 1, "entries": []}
                desired = merge_entries(base, json.loads(args.candidates.read_bytes()))
            output(tx.save_plan(args.out, tx.plan_library(args.library, desired)))
        elif args.command == "preview":
            plan = tx.load_plan(args.plan)
            output({"id": tx.plan_id(plan), "plan": plan})
        elif args.command == "apply":
            output(tx.apply_file_plan(tx.load_plan(args.plan), args.approve, args.state))
        return 0
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
