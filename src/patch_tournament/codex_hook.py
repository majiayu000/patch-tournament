from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from .git_snapshot import (
    capture_task_inspection,
    create_worktree_snapshot,
    read_worktree_snapshot,
    write_worktree_snapshot,
)
from .guard import GuardResult, evaluate_guard


def _required_text(event: Mapping[str, object], key: str) -> str:
    value = event.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"hook event requires a non-empty {key}")
    return value


def _repository_root(cwd: Path) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def _snapshot_path(
    plugin_data: Path,
    *,
    repository: Path,
    session_id: str,
    turn_id: str,
) -> Path:
    identity = "\0".join((str(repository), session_id, turn_id)).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()
    return plugin_data / "snapshots" / f"{digest}.json"


def _report_message(result: GuardResult) -> str:
    changed_lines = (
        "unknown (binary files present)"
        if result.facts.text_changed_lines is None
        else str(result.facts.text_changed_lines)
    )
    lines = [
        "[PATCH-GUARD] [info] [this-edit] "
        f"OBSERVATION: status={result.status}; "
        f"changed_files={result.facts.total_file_count}; "
        f"text_changed_lines={changed_lines}",
        "FILES:",
    ]
    for path in result.facts.changed_files:
        stats = result.facts.line_stats[path]
        added = "?" if stats["added"] is None else str(stats["added"])
        deleted = "?" if stats["deleted"] is None else str(stats["deleted"])
        lines.append(f"{result.facts.statuses[path]} {path} (+{added}/-{deleted})")
    lines.extend(
        [
            "FIX: No automatic change is required; review these task-owned paths only "
            "when investigating scope.",
            "DO NOT: Treat this report as proof that tests passed, alter required work "
            "merely to shrink the diff, or modify unrelated files.",
        ]
    )
    return "\n".join(lines)


def handle_event(event: Mapping[str, object], plugin_data: Path) -> dict[str, object]:
    event_name = _required_text(event, "hook_event_name")
    if event_name not in {"PreToolUse", "Stop"}:
        return {}

    cwd = Path(_required_text(event, "cwd")).resolve()
    session_id = _required_text(event, "session_id")
    turn_id = _required_text(event, "turn_id")
    repository = _repository_root(cwd)
    if repository is None:
        return {}

    snapshot_path = _snapshot_path(
        plugin_data,
        repository=repository,
        session_id=session_id,
        turn_id=turn_id,
    )
    if event_name == "PreToolUse":
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        if snapshot_path.exists():
            return {}
        snapshot = create_worktree_snapshot(repository)
        try:
            write_worktree_snapshot(snapshot, snapshot_path)
        except FileExistsError:
            return {}
        return {}

    if event.get("stop_hook_active") is True or not snapshot_path.is_file():
        return {}
    snapshot = read_worktree_snapshot(snapshot_path)
    inspection = capture_task_inspection(repository, snapshot)
    result = evaluate_guard(inspection)
    if result.status == "empty":
        return {}
    return {"systemMessage": _report_message(result)}


def _error_payload(error: Exception, event_name: object = None) -> dict[str, object]:
    observation = (
        "[PATCH-GUARD-ERROR] [review] [this-edit] OBSERVATION: "
        f"task attribution unavailable: {error}"
    )
    guidance = (
        "FIX: Report that task-level attribution is unavailable for this turn.\n"
        "DO NOT: Claim a verified task diff or create a retrospective baseline."
    )
    payload: dict[str, object] = {"systemMessage": observation}
    if event_name == "Stop":
        payload.update({"decision": "block", "reason": f"{observation}\n{guidance}"})
    return payload


def main() -> int:
    event: object = None
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("hook input must be a JSON object")
        plugin_data_raw = os.environ.get("PLUGIN_DATA")
        if not plugin_data_raw:
            raise ValueError("PLUGIN_DATA is not set")
        payload = handle_event(event, Path(plugin_data_raw))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        event_name = event.get("hook_event_name") if isinstance(event, dict) else None
        payload = _error_payload(error, event_name)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
