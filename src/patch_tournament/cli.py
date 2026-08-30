from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .runner import run_tournament


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patch-tournament",
        description="Compare generated patches using independent evidence and deterministic selection.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run one report-only patch tournament")
    run.add_argument("--config", type=Path, required=True, help="path to the TOML evidence bundle")
    run.add_argument("--output", type=Path, required=True, help="new directory for reports and patches")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_tournament(args.config, args.output)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"patch-tournament: error: {error}", file=sys.stderr)
        return 1
    print(f"status={result.status}")
    print(f"winner={result.winner_id or 'none'}")
    print(f"report={result.report_path}")
    return 0 if result.winner_id else 2


if __name__ == "__main__":
    raise SystemExit(main())
