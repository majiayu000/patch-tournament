from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import CandidateConfig, SourceConfig


@dataclass(frozen=True)
class Invocation:
    args: tuple[str, ...]
    env: dict[str, str]


def build_task_prompt(sources: tuple[SourceConfig, ...]) -> str:
    sections = [
        "Implement the requested change in the current repository. "
        "Keep the patch focused and verify it with repository-provided checks.",
    ]
    for source in sources:
        if not source.visible:
            continue
        try:
            content = source.path.read_text(encoding="utf-8")
        except OSError as error:
            raise RuntimeError(f"cannot read visible evidence {source.path}: {error}") from error
        sections.append(
            f"--- SOURCE kind={source.kind} path={source.path.name} ---\n{content.rstrip()}"
        )
    return "\n\n".join(sections) + "\n"


def build_candidate_invocation(
    config: CandidateConfig, workspace: Path, prompt: str
) -> Invocation:
    if config.adapter == "command":
        return Invocation(config.command, {})
    if config.adapter != "codex":
        raise ValueError(f"unsupported candidate adapter: {config.adapter}")
    args: list[str] = [
        "codex", "exec", "--ephemeral", "--json", "--ignore-user-config",
        "--sandbox", "workspace-write",
    ]
    if config.model:
        args.extend(("--model", config.model))
    if config.reasoning_effort:
        args.extend(("-c", f'model_reasoning_effort="{config.reasoning_effort}"'))
    args.extend(("--cd", str(workspace.absolute()), prompt))
    return Invocation(tuple(args), {})


def prepare_codex_home(source: Path, destination: Path) -> None:
    auth = source.expanduser().resolve() / "auth.json"
    if not auth.is_file():
        raise FileNotFoundError(f"Codex auth file does not exist: {auth}")
    destination.mkdir(parents=True, exist_ok=False)
    target = destination / "auth.json"
    shutil.copyfile(auth, target)
    target.chmod(0o600)
