from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping, Sequence


@dataclass(frozen=True)
class PatchMetrics:
    dependency_manifest_count: int
    dependency_manifest_files: tuple[str, ...]
    production_file_count: int
    production_files: tuple[str, ...]
    production_changed_lines: int
    test_files: tuple[str, ...]
    total_file_count: int
    total_changed_lines: int


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate_id: str
    correct: bool
    failures: tuple[str, ...]
    metrics: PatchMetrics


@dataclass(frozen=True)
class SelectionResult:
    status: str
    winner_id: str | None
    eligible_count: int
    ranked: tuple[CandidateEvaluation, ...]


def _matches(path: str, patterns: Sequence[str]) -> bool:
    posix = PurePosixPath(path)
    return any(posix.match(pattern) or fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def inspect_metrics(
    changed_files: Sequence[str],
    line_stats: Mapping[str, Mapping[str, int | None]],
    *,
    test_globs: Sequence[str],
    dependency_manifests: Sequence[str],
) -> PatchMetrics:
    files = tuple(sorted(set(changed_files)))
    manifests = set(dependency_manifests)
    dependencies = tuple(
        path for path in files if path in manifests or PurePosixPath(path).name in manifests
    )
    tests = tuple(path for path in files if _matches(path, test_globs))
    excluded = set(dependencies) | set(tests)
    production = tuple(path for path in files if path not in excluded)

    def changed_lines(path: str) -> int:
        stats = line_stats.get(path, {})
        added, deleted = stats.get("added", 0), stats.get("deleted", 0)
        return (added if isinstance(added, int) else 1_000_000) + (
            deleted if isinstance(deleted, int) else 1_000_000
        )

    return PatchMetrics(
        dependency_manifest_count=len(dependencies),
        dependency_manifest_files=dependencies,
        production_file_count=len(production),
        production_files=production,
        production_changed_lines=sum(changed_lines(path) for path in production),
        test_files=tests,
        total_file_count=len(files),
        total_changed_lines=sum(changed_lines(path) for path in files),
    )


def _rank(item: CandidateEvaluation) -> tuple[int, int, int, int, int, str]:
    metric = item.metrics
    return (
        metric.dependency_manifest_count,
        metric.production_file_count,
        metric.production_changed_lines,
        metric.total_file_count,
        metric.total_changed_lines,
        item.candidate_id,
    )


def select_winner(evaluations: Sequence[CandidateEvaluation]) -> SelectionResult:
    eligible = sorted((item for item in evaluations if item.correct), key=_rank)
    ineligible = sorted(
        (item for item in evaluations if not item.correct), key=lambda item: item.candidate_id
    )
    ranked = tuple(eligible + ineligible)
    if not eligible:
        return SelectionResult("no_winner", None, 0, ranked)
    return SelectionResult("winner", eligible[0].candidate_id, len(eligible), ranked)
