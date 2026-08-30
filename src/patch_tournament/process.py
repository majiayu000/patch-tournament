from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CommandResult:
    status: str
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def passed(self) -> bool:
        return self.status == "passed"


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def run_command(
    args: Sequence[str],
    cwd: Path,
    *,
    timeout_seconds: int,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    started = time.monotonic()
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    try:
        result = subprocess.run(
            list(args),
            cwd=cwd,
            env=process_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        return CommandResult(
            "timeout", None, _text(error.stdout), _text(error.stderr), time.monotonic() - started
        )
    except OSError as error:
        return CommandResult("error", None, "", str(error), time.monotonic() - started)
    return CommandResult(
        "passed" if result.returncode == 0 else "failed",
        result.returncode,
        result.stdout,
        result.stderr,
        time.monotonic() - started,
    )
