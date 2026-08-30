from __future__ import annotations

import subprocess
from pathlib import Path


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def init_repo(path: Path, files: dict[str, str]) -> str:
    path.mkdir(parents=True)
    result = run(["git", "init", "--quiet"], path)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    run(["git", "config", "user.name", "Patch Tournament Tests"], path)
    run(["git", "config", "user.email", "tests@example.invalid"], path)
    for relative, content in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    run(["git", "add", "-A"], path)
    result = run(["git", "commit", "--quiet", "-m", "baseline"], path)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return run(["git", "rev-parse", "HEAD"], path).stdout.strip()
