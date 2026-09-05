from __future__ import annotations

import json
import os
import posixpath
import subprocess
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from pathlib import PurePosixPath


BASELINE_REF = "refs/patch-tournament/baseline"


@dataclass(frozen=True)
class GitInspection:
    changed_files: tuple[str, ...]
    line_stats: dict[str, dict[str, int | None]]
    patch: str
    statuses: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WorktreeSnapshot:
    repository: str
    base_commit: str
    inspection: GitInspection


SNAPSHOT_SCHEMA_VERSION = 2


def _git(
    args: list[str], cwd: Path, *, text: bool = True, input: bytes | None = None
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=text, input=input, check=False
    )
    if result.returncode != 0:
        stderr = result.stderr if text else result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {stderr.strip()}")
    return result


def create_snapshot(source: Path, ref: str, destination: Path) -> str:
    source, destination = source.resolve(), destination.resolve()
    if destination.exists():
        raise FileExistsError(f"snapshot destination already exists: {destination}")
    destination.mkdir(parents=True)
    entries = []
    for record in _git(["ls-tree", "-r", "-z", ref], source).stdout.split("\0"):
        if not record:
            continue
        metadata, path = record.split("\t", 1)
        mode, kind, object_id = metadata.split()
        _validate_relative_path(path)
        if kind != "blob" or mode not in {"100644", "100755", "120000"}:
            raise RuntimeError(f"unsupported Git entry in snapshot: {path} ({mode})")
        entries.append((mode, path, object_id))
    # Read committed blobs directly: archive attributes must not omit or rewrite files.
    if entries:
        objects = BytesIO(_git(
            ["cat-file", "--batch"], source, text=False,
            input="".join(f"{oid}\n" for _, _, oid in entries).encode("ascii"),
        ).stdout)
        for mode, path, object_id in entries:
            oid, kind, size = objects.readline().decode("ascii").split()
            if oid != object_id or kind != "blob":
                raise RuntimeError(f"unexpected Git object for snapshot: {path}")
            content = objects.read(int(size))
            if len(content) != int(size) or objects.read(1) != b"\n":
                raise RuntimeError(f"truncated Git blob for snapshot: {path}")
            target_path = destination / path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if mode == "120000":
                target = PurePosixPath(os.fsdecode(content))
                resolved = posixpath.normpath(str(PurePosixPath(path).parent / target))
                if target.is_absolute() or resolved == ".." or resolved.startswith("../"):
                    raise RuntimeError(f"Git link escapes snapshot: {path}")
                target_path.symlink_to(os.fsdecode(content))
            else:
                target_path.write_bytes(content)
                target_path.chmod(int(mode, 8) & 0o777)
    _git(["init", "--quiet"], destination)
    _git(["config", "user.name", "Patch Tournament"], destination)
    _git(["config", "user.email", "patch-tournament@example.invalid"], destination)
    _git(["add", "--force", "-A"], destination)
    _git(
        [
            "commit", "--no-gpg-sign", "--allow-empty", "--quiet", "-m",
            "patch-tournament baseline",
        ],
        destination,
    )
    head = _git(["rev-parse", "HEAD"], destination).stdout.strip()
    _git(["update-ref", BASELINE_REF, head], destination)
    return head


def capture_inspection(workspace: Path) -> GitInspection:
    workspace = workspace.resolve()
    _git(["add", "-N", "--all"], workspace)
    names = _git(
        ["diff", "--no-renames", "--name-only", "-z", BASELINE_REF, "--"], workspace
    ).stdout.split("\0")
    changed_files = tuple(sorted(line for line in names if line))
    stats = _parse_numstat_z(
        _git(["diff", "--no-renames", "--numstat", "-z", BASELINE_REF, "--"], workspace).stdout
    )
    patch = _git(["diff", "--no-renames", "--binary", "--full-index", BASELINE_REF, "--"], workspace).stdout
    return GitInspection(changed_files, stats, patch)


def _numstat_counts(added_raw: str, deleted_raw: str) -> dict[str, int | None]:
    return {
        "added": int(added_raw) if added_raw.isdigit() else None,
        "deleted": int(deleted_raw) if deleted_raw.isdigit() else None,
    }


def _parse_numstat_z(output: str) -> dict[str, dict[str, int | None]]:
    stats: dict[str, dict[str, int | None]] = {}
    for record in (record for record in output.split("\0") if record):
        added_raw, deleted_raw, path = record.split("\t", maxsplit=2)
        stats[path] = _numstat_counts(added_raw, deleted_raw)
    return stats


def _untracked_diff(workspace: Path, path: str, *, numstat: bool = False) -> str:
    args = ["git", "diff", "--no-index", "--no-renames"]
    args.extend(["--numstat"] if numstat else ["--binary", "--full-index"])
    args.extend(["--", "/dev/null", path])
    result = subprocess.run(
        args, cwd=workspace, capture_output=True, text=True, check=False
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"git diff for untracked file {path} failed: {result.stderr.strip()}")
    return result.stdout


def capture_worktree_inspection(workspace: Path, base: str) -> GitInspection:
    """Inspect tracked and untracked changes without modifying the Git index."""
    workspace = workspace.resolve()
    statuses: dict[str, str] = {}
    status_output = _git(
        ["diff", "--no-renames", "--name-status", "-z", base, "--"], workspace
    ).stdout
    status_fields = [field for field in status_output.split("\0") if field]
    if len(status_fields) % 2:
        raise RuntimeError("git returned malformed name-status output")
    for index in range(0, len(status_fields), 2):
        status, path = status_fields[index : index + 2]
        statuses[path] = status

    stats = _parse_numstat_z(
        _git(
            ["diff", "--no-renames", "--numstat", "-z", base, "--"], workspace
        ).stdout
    )
    patches = [
        _git(
            ["diff", "--no-renames", "--binary", "--full-index", base, "--"],
            workspace,
        ).stdout
    ]
    untracked_output = _git(
        ["ls-files", "--others", "--exclude-standard", "-z"], workspace
    ).stdout
    for path in sorted(path for path in untracked_output.split("\0") if path):
        statuses[path] = "A"
        numstat = _untracked_diff(workspace, path, numstat=True).splitlines()
        if numstat:
            added_raw, deleted_raw, _ = numstat[0].split("\t", maxsplit=2)
            stats[path] = _numstat_counts(added_raw, deleted_raw)
        else:
            stats[path] = {"added": 0, "deleted": 0}
        patches.append(_untracked_diff(workspace, path))

    return GitInspection(tuple(sorted(statuses)), stats, "".join(patches), statuses)


def create_worktree_snapshot(workspace: Path, base: str = "HEAD") -> WorktreeSnapshot:
    """Capture the repository state that exists before an agent starts work."""
    workspace = workspace.resolve()
    repository = Path(
        _git(["rev-parse", "--show-toplevel"], workspace).stdout.strip()
    ).resolve()
    base_commit = _git(
        ["rev-parse", "--verify", f"{base}^{{commit}}"], repository
    ).stdout.strip()
    return WorktreeSnapshot(
        repository=str(repository),
        base_commit=base_commit,
        inspection=capture_worktree_inspection(repository, base_commit),
    )


def write_worktree_snapshot(snapshot: WorktreeSnapshot, output: Path) -> None:
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "kind": "worktree_snapshot",
        "repository": snapshot.repository,
        "base_commit": snapshot.base_commit,
        "inspection": {
            "changed_files": list(snapshot.inspection.changed_files),
            "line_stats": snapshot.inspection.line_stats,
            "patch": snapshot.inspection.patch,
            "statuses": snapshot.inspection.statuses,
        },
    }
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with output.open("x", encoding="utf-8") as stream:
        stream.write(serialized)


def read_worktree_snapshot(path: Path) -> WorktreeSnapshot:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid snapshot JSON in {path}: {error.msg}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"invalid snapshot in {path}: root must be an object")
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported snapshot schema in {path}: {payload.get('schema_version')!r}"
        )
    if payload.get("kind") != "worktree_snapshot":
        raise ValueError(f"invalid snapshot kind in {path}: {payload.get('kind')!r}")
    repository = payload.get("repository")
    base_commit = payload.get("base_commit")
    raw_inspection = payload.get("inspection")
    if not isinstance(repository, str) or not repository:
        raise ValueError(f"invalid snapshot in {path}: repository must be a string")
    if not isinstance(base_commit, str) or not base_commit:
        raise ValueError(f"invalid snapshot in {path}: base_commit must be a string")
    if not isinstance(raw_inspection, dict):
        raise ValueError(f"invalid snapshot in {path}: inspection must be an object")
    changed_files = raw_inspection.get("changed_files")
    line_stats = raw_inspection.get("line_stats")
    patch = raw_inspection.get("patch")
    statuses = raw_inspection.get("statuses")
    if not isinstance(changed_files, list) or not all(
        isinstance(item, str) for item in changed_files
    ):
        raise ValueError(f"invalid snapshot in {path}: changed_files must be strings")
    if not isinstance(line_stats, dict) or not isinstance(statuses, dict):
        raise ValueError(f"invalid snapshot in {path}: line_stats and statuses must be objects")
    if not isinstance(patch, str):
        raise ValueError(f"invalid snapshot in {path}: patch must be a string")
    for changed_path in changed_files:
        _validate_relative_path(changed_path)
    normalized_stats: dict[str, dict[str, int | None]] = {}
    for changed_path, values in line_stats.items():
        if not isinstance(changed_path, str) or not isinstance(values, dict):
            raise ValueError(f"invalid snapshot in {path}: malformed line_stats")
        added, deleted = values.get("added"), values.get("deleted")
        if not all(value is None or isinstance(value, int) for value in (added, deleted)):
            raise ValueError(f"invalid snapshot in {path}: malformed line count")
        normalized_stats[changed_path] = {"added": added, "deleted": deleted}
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in statuses.items()
    ):
        raise ValueError(f"invalid snapshot in {path}: malformed statuses")
    return WorktreeSnapshot(
        repository=repository,
        base_commit=base_commit,
        inspection=GitInspection(
            changed_files=tuple(changed_files),
            line_stats=normalized_stats,
            patch=patch,
            statuses=dict(statuses),
        ),
    )


def _validate_relative_path(path: str) -> None:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise RuntimeError(f"unsafe path in worktree snapshot: {path!r}")


def _path_state(path: Path) -> tuple[str, bool, bytes | str] | None:
    if not os.path.lexists(path):
        return None
    if path.is_symlink():
        return ("symlink", False, os.readlink(path))
    if not path.is_file():
        raise RuntimeError(f"unsupported worktree entry: {path}")
    return ("file", bool(path.stat().st_mode & 0o111), path.read_bytes())


def _task_numstat(before: Path, after: Path) -> dict[str, int | None]:
    before_arg = str(before) if os.path.lexists(before) else "/dev/null"
    after_arg = str(after) if os.path.lexists(after) else "/dev/null"
    result = subprocess.run(
        [
            "git", "diff", "--no-index", "--no-renames", "--numstat", "--",
            before_arg, after_arg,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(
            f"git diff failed while comparing task state: {result.stderr.strip()}"
        )
    if not result.stdout.strip():
        return {"added": 0, "deleted": 0}
    added_raw, deleted_raw, _ = result.stdout.splitlines()[0].split("\t", maxsplit=2)
    return _numstat_counts(added_raw, deleted_raw)


def capture_task_inspection(
    workspace: Path, snapshot: WorktreeSnapshot
) -> GitInspection:
    """Return only changes made after ``snapshot`` was captured."""
    workspace = workspace.resolve()
    repository = Path(
        _git(["rev-parse", "--show-toplevel"], workspace).stdout.strip()
    ).resolve()
    if repository != Path(snapshot.repository).resolve():
        raise RuntimeError(
            f"snapshot belongs to {snapshot.repository}, not repository {repository}"
        )

    final_inspection = capture_worktree_inspection(repository, snapshot.base_commit)
    candidates = sorted(
        set(snapshot.inspection.changed_files) | set(final_inspection.changed_files)
    )
    for path in candidates:
        _validate_relative_path(path)

    with tempfile.TemporaryDirectory(prefix="patch-tournament-start-") as raw:
        start = Path(raw) / "repository"
        create_snapshot(repository, snapshot.base_commit, start)
        if snapshot.inspection.patch:
            apply_patch_text(start, snapshot.inspection.patch)
        for path, status in snapshot.inspection.statuses.items():
            _validate_relative_path(path)
            entry = start / path
            if status == "A" and not os.path.lexists(entry):
                entry.parent.mkdir(parents=True, exist_ok=True)
                entry.touch()

        statuses: dict[str, str] = {}
        stats: dict[str, dict[str, int | None]] = {}
        for path in candidates:
            before = start / path
            after = repository / path
            before_state = _path_state(before)
            after_state = _path_state(after)
            if before_state == after_state:
                continue
            if before_state is None:
                statuses[path] = "A"
            elif after_state is None:
                statuses[path] = "D"
            else:
                statuses[path] = "M"
            stats[path] = _task_numstat(before, after)

    return GitInspection(tuple(statuses), stats, "", statuses)


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
