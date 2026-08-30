from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from . import __version__
from .git_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    capture_task_inspection,
    create_worktree_snapshot,
    read_worktree_snapshot,
    write_worktree_snapshot,
)
from .guard import GuardResult, evaluate_guard
from .runner import run_tournament


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patch-tournament",
        description="Report task-diff facts or run an explicit patch tournament.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run one report-only patch tournament")
    run.add_argument(
        "--config", type=Path, required=True, help="path to the TOML evidence bundle"
    )
    run.add_argument(
        "--output", type=Path, required=True, help="new directory for reports and patches"
    )

    snapshot = subparsers.add_parser(
        "snapshot", help="record repository state before an agent starts work"
    )
    snapshot.add_argument("--repo", type=Path, default=Path.cwd(), help="Git repository")
    snapshot.add_argument("--base", default="HEAD", help="Git revision used as the base")
    snapshot.add_argument("--output", type=Path, required=True, help="new snapshot JSON file")
    snapshot.add_argument("--format", choices=("json", "text"), default="text")

    guard = subparsers.add_parser(
        "guard", help="report changes made after a task snapshot"
    )
    guard.add_argument("--repo", type=Path, default=Path.cwd(), help="Git repository")
    guard.add_argument("--snapshot", type=Path, required=True, help="task-start snapshot JSON")
    guard.add_argument(
        "--protect", action="append", default=[], help="caller-protected path or glob"
    )
    guard.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def _guard_payload(result: GuardResult) -> dict[str, object]:
    return {"schema_version": SNAPSHOT_SCHEMA_VERSION, **asdict(result)}


def _print_guard(result: GuardResult, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(_guard_payload(result), indent=2, sort_keys=True))
        return
    print(f"status={result.status}")
    print(f"changed_files={result.facts.total_file_count}")
    if result.facts.text_changed_lines is None:
        print("text_changed_lines=unknown (binary files present)")
    else:
        print(f"text_changed_lines={result.facts.text_changed_lines}")
    for path in result.facts.changed_files:
        print(f"{result.facts.statuses.get(path, 'M')} {path}")
    for violation in result.violations:
        print(f"violation: {violation.code}: {violation.message}")
        for path in violation.paths:
            print(f"  {path}")


def _run_snapshot(args: argparse.Namespace) -> int:
    snapshot = create_worktree_snapshot(args.repo, args.base)
    write_worktree_snapshot(snapshot, args.output)
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "status": "snapshot_created",
        "snapshot": str(args.output.resolve()),
        "repository": snapshot.repository,
        "base_commit": snapshot.base_commit,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("status=snapshot_created")
        print(f"snapshot={args.output.resolve()}")
    return 0


def _run_guard(args: argparse.Namespace) -> int:
    snapshot = read_worktree_snapshot(args.snapshot)
    inspection = capture_task_inspection(args.repo, snapshot)
    result = evaluate_guard(inspection, protected_paths=tuple(args.protect))
    _print_guard(result, args.format)
    return 3 if result.status == "constraint_violation" else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            return _run_snapshot(args)
        if args.command == "guard":
            return _run_guard(args)
        result = run_tournament(args.config, args.output)
    except (OSError, RuntimeError, ValueError) as error:
        if getattr(args, "format", None) == "json":
            print(json.dumps(
                {
                    "schema_version": SNAPSHOT_SCHEMA_VERSION,
                    "status": "error",
                    "error": str(error),
                },
                indent=2,
                sort_keys=True,
            ))
        else:
            print(f"patch-tournament: error: {error}", file=sys.stderr)
        return 1
    print(f"status={result.status}")
    print(f"winner={result.winner_id or 'none'}")
    print(f"report={result.report_path}")
    return 0 if result.winner_id else 2


if __name__ == "__main__":
    raise SystemExit(main())
