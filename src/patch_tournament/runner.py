from __future__ import annotations

import json
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from .adapters import build_candidate_invocation, build_task_prompt, prepare_codex_home
from .config import CheckConfig, TournamentConfig, load_config
from .git_snapshot import GitInspection, apply_patch_text, capture_inspection, create_snapshot
from .process import CommandResult, run_command
from .selection import CandidateEvaluation, PatchMetrics, inspect_metrics, select_winner


class TournamentError(RuntimeError):
    """A tournament cannot run safely or produce a trustworthy result."""


@dataclass(frozen=True)
class CheckExecution:
    id: str
    kind: str
    gating: bool
    result: CommandResult


@dataclass(frozen=True)
class CandidateOutcome:
    candidate_id: str
    status: str
    failures: tuple[str, ...]
    generation: CommandResult
    checks: tuple[CheckExecution, ...]
    inspection: GitInspection
    metrics: PatchMetrics


@dataclass(frozen=True)
class TournamentRunResult:
    status: str
    winner_id: str | None
    eligible_count: int
    report_path: Path


def _empty_metrics(config: TournamentConfig) -> PatchMetrics:
    return inspect_metrics(
        (), {},
        test_globs=config.selection.test_globs,
        dependency_manifests=config.selection.dependency_manifests,
    )


def _copy_overlays(config: TournamentConfig, workspace: Path) -> None:
    for overlay in config.overlays:
        destination = workspace / overlay.destination
        if destination.exists():
            raise TournamentError(
                f"overlay destination already exists and will not be overwritten: {overlay.destination}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(overlay.source, destination)


def _run_checks(config: TournamentConfig, workspace: Path) -> tuple[CheckExecution, ...]:
    return tuple(
        CheckExecution(
            check.id,
            check.kind,
            check.gating,
            run_command(check.command, workspace, timeout_seconds=check.timeout_seconds),
        )
        for check in config.checks
    )


def _baseline_matches(check: CheckConfig, result: CommandResult) -> bool:
    if result.status in {"timeout", "error"}:
        return False
    if check.baseline == "any":
        return True
    if check.baseline == "pass":
        return result.passed
    return result.status == "failed"


def _verify_baseline(config: TournamentConfig, temp_root: Path) -> None:
    workspace = temp_root / "baseline"
    create_snapshot(config.project.repo, config.project.ref, workspace)
    _copy_overlays(config, workspace)
    for check in config.checks:
        for path in check.evidence_paths:
            evidence = workspace / path
            if not evidence.is_file() or evidence.resolve() != workspace.resolve() / path:
                raise TournamentError(f"check {check.id}: evidence must be a regular file without symlink parents: {path}")
    executions = _run_checks(config, workspace)
    mismatches = [
        f"{check.id}: expected {check.baseline}, got {execution.result.status}"
        for check, execution in zip(config.checks, executions)
        if not _baseline_matches(check, execution.result)
    ]
    if mismatches:
        raise TournamentError("baseline preflight failed: " + "; ".join(mismatches))


def _candidate_id(index: int) -> str:
    return f"c{index:02d}"


def _run_candidate(
    config: TournamentConfig,
    prompt: str,
    temp_root: Path,
    candidate_id: str,
) -> CandidateOutcome:
    workspace = temp_root / candidate_id
    create_snapshot(config.project.repo, config.project.ref, workspace)
    invocation = build_candidate_invocation(config.candidates, workspace, prompt)
    env = {
        **invocation.env,
        "PATCH_TOURNAMENT_CANDIDATE_ID": candidate_id,
        "PATCH_TOURNAMENT_PROMPT": prompt,
        "PATCH_TOURNAMENT_WORKSPACE": str(workspace),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if config.candidates.adapter == "codex":
        codex_home = temp_root / f"{candidate_id}-codex-home"
        source_home = config.candidates.codex_home or (Path.home() / ".codex")
        prepare_codex_home(source_home, codex_home)
        env["CODEX_HOME"] = str(codex_home)

    generation = run_command(
        invocation.args,
        workspace,
        timeout_seconds=config.candidates.timeout_seconds,
        env=env,
    )
    if generation.status != "passed":
        return CandidateOutcome(
            candidate_id, "ineligible", (f"generation:{generation.status}",), generation, (),
            GitInspection((), {}, ""), _empty_metrics(config),
        )

    inspection = capture_inspection(workspace)
    metrics = inspect_metrics(
        inspection.changed_files,
        inspection.line_stats,
        test_globs=config.selection.test_globs,
        dependency_manifests=config.selection.dependency_manifests,
    )
    failures: list[str] = []
    if not inspection.patch:
        failures.append("empty_patch")
    protected = set(config.safety.protected_paths)
    protected.update(path for check in config.checks if check.gating for path in check.evidence_paths)
    protected.update(str(overlay.destination) for overlay in config.overlays)
    touched_protected = sorted(
        path for path in inspection.changed_files
        if any(boundary == path or boundary.startswith(path + "/") for boundary in protected)
    )
    failures.extend(f"protected_path:{path}" for path in touched_protected)

    checks: tuple[CheckExecution, ...] = ()
    if not failures:
        grader = temp_root / f"{candidate_id}-grader"
        create_snapshot(config.project.repo, config.project.ref, grader)
        try:
            apply_patch_text(grader, inspection.patch)
            _copy_overlays(config, grader)
            checks = _run_checks(config, grader)
        except (OSError, RuntimeError) as error:
            failures.append(f"grader_setup:{error}")
        else:
            failures.extend(
                f"check:{check.id}:{check.result.status}"
                for check in checks
                if check.gating and not check.result.passed
            )
    return CandidateOutcome(
        candidate_id,
        "eligible" if not failures else "ineligible",
        tuple(failures),
        generation,
        checks,
        inspection,
        metrics,
    )


def _command_json(result: CommandResult) -> dict[str, object]:
    return {
        "status": result.status,
        "returncode": result.returncode,
        "duration_seconds": round(result.duration_seconds, 3),
        "stdout": result.stdout[-20_000:],
        "stderr": result.stderr[-20_000:],
    }


def _candidate_json(outcome: CandidateOutcome) -> dict[str, object]:
    return {
        "status": outcome.status,
        "failures": list(outcome.failures),
        "changed_files": list(outcome.inspection.changed_files),
        "metrics": asdict(outcome.metrics),
        "generation": _command_json(outcome.generation),
        "checks": [
            {
                "id": check.id,
                "kind": check.kind,
                "gating": check.gating,
                "result": _command_json(check.result),
            }
            for check in outcome.checks
        ],
    }


def _write_artifacts(
    output: Path,
    selection_status: str,
    winner_id: str | None,
    eligible_count: int,
    outcomes: tuple[CandidateOutcome, ...],
) -> Path:
    output.mkdir(parents=True, exist_ok=False)
    candidates_dir = output / "candidates"
    candidates_dir.mkdir()
    by_id = {item.candidate_id: item for item in outcomes}
    for outcome in outcomes:
        (candidates_dir / f"{outcome.candidate_id}.patch").write_text(
            outcome.inspection.patch, encoding="utf-8"
        )
    if winner_id:
        (output / "winner.patch").write_text(by_id[winner_id].inspection.patch, encoding="utf-8")

    report = {
        "schema_version": 1,
        "status": selection_status,
        "winner_id": winner_id,
        "eligible_count": eligible_count,
        "candidates": {item.candidate_id: _candidate_json(item) for item in outcomes},
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Patch Tournament Report",
        "",
        f"- Status: `{selection_status}`",
        f"- Winner: `{winner_id or 'none'}`",
        f"- Eligible candidates: {eligible_count}",
        "",
        "| Candidate | Status | Production files | Production lines | Failures |",
        "|---|---:|---:|---:|---|",
    ]
    for outcome in outcomes:
        lines.append(
            f"| {outcome.candidate_id} | {outcome.status} | "
            f"{outcome.metrics.production_file_count} | "
            f"{outcome.metrics.production_changed_lines} | "
            f"{', '.join(outcome.failures) or '-'} |"
        )
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def run_tournament(config_path: Path, output: Path) -> TournamentRunResult:
    config = load_config(config_path)
    output = output.resolve()
    if output.exists():
        raise TournamentError(f"output path already exists: {output}")
    try:
        output.relative_to(config.project.repo)
    except ValueError:
        pass
    else:
        raise TournamentError("output path must be outside the source repository")
    prompt = build_task_prompt(config.sources)
    with tempfile.TemporaryDirectory(prefix="patch-tournament-") as raw:
        temp_root = Path(raw)
        _verify_baseline(config, temp_root)
        candidate_ids = tuple(_candidate_id(index) for index in range(1, config.candidates.count + 1))
        with ThreadPoolExecutor(max_workers=config.candidates.concurrency) as executor:
            outcomes = tuple(executor.map(
                lambda candidate_id: _run_candidate(config, prompt, temp_root, candidate_id),
                candidate_ids,
            ))

        evaluations = tuple(
            CandidateEvaluation(
                item.candidate_id, item.status == "eligible", item.failures, item.metrics
            )
            for item in outcomes
        )
        selection = select_winner(evaluations)
        report_path = _write_artifacts(
            output, selection.status, selection.winner_id, selection.eligible_count, outcomes
        )
    return TournamentRunResult(
        selection.status, selection.winner_id, selection.eligible_count, report_path
    )
