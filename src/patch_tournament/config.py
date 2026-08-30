from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class ConfigError(ValueError):
    """The evidence bundle is missing, invalid, or unsafe."""


@dataclass(frozen=True)
class ProjectConfig:
    repo: Path
    ref: str


@dataclass(frozen=True)
class SourceConfig:
    kind: str
    path: Path
    visible: bool


@dataclass(frozen=True)
class CandidateConfig:
    adapter: str
    command: tuple[str, ...]
    count: int
    concurrency: int
    timeout_seconds: int
    model: str | None = None
    reasoning_effort: str | None = None
    codex_home: Path | None = None


@dataclass(frozen=True)
class CheckConfig:
    id: str
    kind: str
    command: tuple[str, ...]
    baseline: str
    timeout_seconds: int

    @property
    def gating(self) -> bool:
        return self.kind != "speculative"


@dataclass(frozen=True)
class OverlayConfig:
    kind: str
    source: Path
    destination: PurePosixPath


@dataclass(frozen=True)
class SelectionConfig:
    test_globs: tuple[str, ...]
    dependency_manifests: tuple[str, ...]


@dataclass(frozen=True)
class SafetyConfig:
    report_only: bool
    protected_paths: tuple[str, ...]


@dataclass(frozen=True)
class TournamentConfig:
    version: int
    project: ProjectConfig
    sources: tuple[SourceConfig, ...]
    candidates: CandidateConfig
    checks: tuple[CheckConfig, ...]
    overlays: tuple[OverlayConfig, ...]
    selection: SelectionConfig
    safety: SafetyConfig


DEFAULT_DEPENDENCY_MANIFESTS = (
    "Cargo.toml", "go.mod", "package.json", "pyproject.toml", "requirements.txt",
)


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a TOML table")
    return value


def _string(table: dict[str, Any], key: str, context: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{context}.{key} must be a non-empty string")
    return value


def _positive_int(table: dict[str, Any], key: str, context: str) -> int:
    value = table.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{context}.{key} must be a positive integer")
    return value


def _command(value: Any, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ConfigError(f"{context}.command must be a non-empty array of arguments")
    return tuple(value)


def _string_tuple(value: Any, context: str, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{context} must be an array of non-empty strings")
    return tuple(value)


def _resolve_existing(base: Path, raw: str, context: str) -> Path:
    value = Path(raw).expanduser()
    resolved = value.resolve() if value.is_absolute() else (base / value).resolve()
    if not resolved.exists():
        raise ConfigError(f"{context} does not exist: {resolved}")
    return resolved


def load_config(path: Path) -> TournamentConfig:
    config_path = path.resolve()
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"cannot read configuration {config_path}: {error}") from error
    if data.get("version") != 1:
        raise ConfigError("version must be 1")
    base = config_path.parent

    raw_project = _table(data, "project")
    project = ProjectConfig(
        _resolve_existing(base, _string(raw_project, "repo", "project"), "project.repo"),
        _string(raw_project, "ref", "project"),
    )

    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ConfigError("[[sources]] must contain at least one source")
    sources: list[SourceConfig] = []
    for index, row in enumerate(raw_sources):
        context = f"sources[{index}]"
        if not isinstance(row, dict):
            raise ConfigError(f"{context} must be a table")
        visible = row.get("visible")
        if not isinstance(visible, bool):
            raise ConfigError(f"{context}.visible must be a boolean")
        sources.append(SourceConfig(
            _string(row, "kind", context),
            _resolve_existing(base, _string(row, "path", context), f"{context}.path"),
            visible,
        ))

    raw_candidates = _table(data, "candidates")
    adapter = _string(raw_candidates, "adapter", "candidates")
    if adapter not in {"command", "codex"}:
        raise ConfigError("candidates.adapter must be 'command' or 'codex'")
    command = _command(raw_candidates.get("command"), "candidates") if adapter == "command" else ()
    raw_home = raw_candidates.get("codex_home")
    candidates = CandidateConfig(
        adapter=adapter,
        command=command,
        count=_positive_int(raw_candidates, "count", "candidates"),
        concurrency=_positive_int(raw_candidates, "concurrency", "candidates"),
        timeout_seconds=_positive_int(raw_candidates, "timeout_seconds", "candidates"),
        model=raw_candidates.get("model") if isinstance(raw_candidates.get("model"), str) else None,
        reasoning_effort=(raw_candidates.get("reasoning_effort")
                          if isinstance(raw_candidates.get("reasoning_effort"), str) else None),
        codex_home=(Path(raw_home).expanduser().resolve() if isinstance(raw_home, str) else None),
    )

    raw_checks = data.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise ConfigError("[[checks]] must contain at least one check")
    checks: list[CheckConfig] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(raw_checks):
        context = f"checks[{index}]"
        if not isinstance(row, dict):
            raise ConfigError(f"{context} must be a table")
        check_id = _string(row, "id", context)
        if check_id in seen_ids:
            raise ConfigError(f"duplicate check id: {check_id}")
        seen_ids.add(check_id)
        kind = _string(row, "kind", context)
        if kind not in {"existing", "reproduction", "approved-hidden", "speculative"}:
            raise ConfigError(f"{context}.kind is not supported: {kind}")
        baseline = _string(row, "baseline", context)
        if baseline not in {"pass", "fail", "any"}:
            raise ConfigError(f"{context}.baseline must be 'pass', 'fail', or 'any'")
        checks.append(CheckConfig(
            check_id, kind, _command(row.get("command"), context), baseline,
            _positive_int(row, "timeout_seconds", context),
        ))

    raw_overlays = data.get("overlays", [])
    if not isinstance(raw_overlays, list):
        raise ConfigError("[[overlays]] must be an array of tables")
    overlays: list[OverlayConfig] = []
    for index, row in enumerate(raw_overlays):
        context = f"overlays[{index}]"
        if not isinstance(row, dict):
            raise ConfigError(f"{context} must be a table")
        destination = PurePosixPath(_string(row, "destination", context))
        if destination.is_absolute() or ".." in destination.parts:
            raise ConfigError(f"{context}.destination must stay inside the grader workspace")
        overlays.append(OverlayConfig(
            _string(row, "kind", context),
            _resolve_existing(base, _string(row, "source", context), f"{context}.source"),
            destination,
        ))

    raw_selection = data.get("selection", {})
    if not isinstance(raw_selection, dict):
        raise ConfigError("[selection] must be a TOML table")
    selection = SelectionConfig(
        _string_tuple(raw_selection.get("test_globs"), "selection.test_globs"),
        _string_tuple(
            raw_selection.get("dependency_manifests"),
            "selection.dependency_manifests",
            default=DEFAULT_DEPENDENCY_MANIFESTS,
        ),
    )

    raw_safety = _table(data, "safety")
    if raw_safety.get("report_only") is not True:
        raise ConfigError("safety.report_only must be true in version 1")
    safety = SafetyConfig(
        True, _string_tuple(raw_safety.get("protected_paths"), "safety.protected_paths"),
    )
    return TournamentConfig(
        1, project, tuple(sources), candidates, tuple(checks), tuple(overlays), selection, safety,
    )
