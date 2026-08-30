from __future__ import annotations

import subprocess
import tarfile
import posixpath
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from pathlib import PurePosixPath


BASELINE_REF = "refs/patch-tournament/baseline"


@dataclass(frozen=True)
class GitInspection:
    changed_files: tuple[str, ...]
    line_stats: dict[str, dict[str, int | None]]
    patch: str


def _git(args: list[str], cwd: Path, *, text: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=text, check=False
    )
    if result.returncode != 0:
        stderr = result.stderr if text else result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {stderr.strip()}")
    return result


def create_snapshot(source: Path, ref: str, destination: Path) -> str:
    source, destination = source.resolve(), destination.resolve()
    if destination.exists():
        raise FileExistsError(f"snapshot destination already exists: {destination}")
    archive = _git(["archive", "--format=tar", ref], source, text=False).stdout
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as bundle:
        for member in bundle.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or member.isdev() or member.isfifo():
                raise RuntimeError(f"unsafe path in git archive: {member.name}")
            if member.issym() or member.islnk():
                target = PurePosixPath(member.linkname)
                resolved_link = posixpath.normpath(str(name.parent / target))
                if target.is_absolute() or resolved_link == ".." or resolved_link.startswith("../"):
                    raise RuntimeError(f"archive link escapes snapshot: {member.name}")
        bundle.extractall(destination)
    _git(["init", "--quiet"], destination)
    _git(["config", "user.name", "Patch Tournament"], destination)
    _git(["config", "user.email", "patch-tournament@example.invalid"], destination)
    _git(["add", "-A"], destination)
    _git(["commit", "--quiet", "-m", "patch-tournament baseline"], destination)
    head = _git(["rev-parse", "HEAD"], destination).stdout.strip()
    _git(["update-ref", BASELINE_REF, head], destination)
    return head


def capture_inspection(workspace: Path) -> GitInspection:
    workspace = workspace.resolve()
    _git(["add", "-N", "--all"], workspace)
    names = _git(["diff", "--name-only", BASELINE_REF, "--"], workspace).stdout.splitlines()
    changed_files = tuple(sorted(line for line in names if line))
    stats: dict[str, dict[str, int | None]] = {}
    output = _git(["diff", "--numstat", BASELINE_REF, "--"], workspace).stdout
    for line in output.splitlines():
        added_raw, deleted_raw, path = line.split("\t", maxsplit=2)
        stats[path] = {
            "added": int(added_raw) if added_raw.isdigit() else None,
            "deleted": int(deleted_raw) if deleted_raw.isdigit() else None,
        }
    patch = _git(["diff", "--binary", "--full-index", BASELINE_REF, "--"], workspace).stdout
    return GitInspection(changed_files, stats, patch)


def apply_patch_text(workspace: Path, patch: str) -> None:
    result = subprocess.run(
        ["git", "apply", "--binary", "--whitespace=nowarn", "-"],
        cwd=workspace,
        input=patch,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git apply failed in {workspace}: {result.stderr.strip()}")
