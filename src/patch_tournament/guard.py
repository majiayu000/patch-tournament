from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Sequence

from .git_snapshot import GitInspection


@dataclass(frozen=True)
class ConstraintViolation:
    code: str
    message: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class PatchFacts:
    changed_files: tuple[str, ...]
    added_files: tuple[str, ...]
    modified_files: tuple[str, ...]
    deleted_files: tuple[str, ...]
    statuses: dict[str, str]
    line_stats: dict[str, dict[str, int | None]]
    binary_files: tuple[str, ...]
    total_file_count: int
    text_changed_lines: int | None
    line_count_complete: bool


@dataclass(frozen=True)
class GuardResult:
    status: str
    facts: PatchFacts
    violations: tuple[ConstraintViolation, ...]


def _matches(path: str, patterns: Sequence[str]) -> bool:
    return any(path == pattern or fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def evaluate_guard(
    inspection: GitInspection,
    *,
    protected_paths: Sequence[str] = (),
) -> GuardResult:
    """Report task-diff facts and enforce only caller-supplied path constraints."""
    added = tuple(
        path
        for path in inspection.changed_files
        if inspection.statuses.get(path, "").startswith("A")
    )
    deleted = tuple(
        path
        for path in inspection.changed_files
        if inspection.statuses.get(path, "").startswith("D")
    )
    terminal_paths = set(added) | set(deleted)
    modified = tuple(
        path for path in inspection.changed_files if path not in terminal_paths
    )
    binary = tuple(
        path for path in inspection.changed_files
        if inspection.line_stats.get(path, {}).get("added") is None
        or inspection.line_stats.get(path, {}).get("deleted") is None
    )
    line_count_complete = not binary
    text_changed_lines = (
        sum(
            int(inspection.line_stats.get(path, {}).get("added", 0) or 0)
            + int(inspection.line_stats.get(path, {}).get("deleted", 0) or 0)
            for path in inspection.changed_files
        )
        if line_count_complete
        else None
    )
    facts = PatchFacts(
        changed_files=inspection.changed_files,
        added_files=added,
        modified_files=modified,
        deleted_files=deleted,
        statuses=inspection.statuses,
        line_stats=inspection.line_stats,
        binary_files=binary,
        total_file_count=len(inspection.changed_files),
        text_changed_lines=text_changed_lines,
        line_count_complete=line_count_complete,
    )

    protected = tuple(
        path for path in inspection.changed_files if _matches(path, protected_paths)
    )
    violations = (
        (
            ConstraintViolation(
                code="protected_path_changed",
                message="The task changed a caller-protected path.",
                paths=protected,
            ),
        )
        if protected
        else ()
    )
    if violations:
        status = "constraint_violation"
    elif not inspection.changed_files:
        status = "empty"
    else:
        status = "observed"
    return GuardResult(status=status, facts=facts, violations=violations)
