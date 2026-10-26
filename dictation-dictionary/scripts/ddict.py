"""Run with uv run python scripts/ddict.py --help."""
import argparse
import csv
import json
import sys
from pathlib import Path

from vocabulary import DEFAULT_LIBRARY, active_words, diff_words, load_library


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
        return 0
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
