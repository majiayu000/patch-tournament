# Patch Tournament

Patch Tournament runs several code agents against isolated snapshots, grades every patch in a separate clean snapshot, and selects the smallest patch that passes independently supplied checks. It produces reports and a `winner.patch`; version 1 never modifies the source repository or applies the winner.

The tool is designed to reduce agent over-design without asking the same agent to invent its own acceptance contract. Humans, CI, issue text, existing tests, or approved hidden reproductions provide the evidence. The tournament only executes and compares it.

## What is enforced

1. A preflight verifies each check's declared baseline (`pass`, `fail`, or `any`).
2. Candidates run concurrently in independent `git archive` snapshots.
3. Non-visible evidence and overlays are withheld from candidates.
4. Each resulting patch is applied to a fresh grader snapshot.
5. `existing`, `reproduction`, and `approved-hidden` checks gate correctness. `speculative` checks are reported but can never gate selection.
6. Correct patches are ranked by dependency-manifest changes, production-file count, production changed lines, total-file count, total changed lines, then candidate ID.

This does not prove that a patch is correct beyond the supplied evidence. Weak checks still produce weak conclusions.

## Install and run

Requirements are Python 3.11+, Git, and optionally the Codex CLI.

```bash
python3 -m pip install -e .
cp examples/tournament.toml.example tournament.toml
patch-tournament run --config tournament.toml --output tournament-result
```

Exit codes are `0` for a winner, `2` when no candidate qualifies, and `1` for an invalid configuration or unsafe preflight.

Outputs include `report.json`, `report.md`, every candidate patch under `candidates/`, and `winner.patch` when a winner exists. The output directory must not already exist.

## Candidate adapters

`adapter = "codex"` invokes `codex exec --ephemeral --json --ignore-user-config --sandbox workspace-write`. Patch Tournament creates a temporary `CODEX_HOME` containing only a mode-`0600` copy of `auth.json`; user-level configuration and global instructions are not copied. Repository `AGENTS.md` files remain part of the selected Git snapshot. See the [Codex non-interactive mode documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

For any other agent, use an argument array rather than a shell string:

```toml
[candidates]
adapter = "command"
command = ["python3", "my_agent.py"]
count = 3
concurrency = 3
timeout_seconds = 600
```

The command runs with its candidate snapshot as the working directory and receives `PATCH_TOURNAMENT_CANDIDATE_ID`, `PATCH_TOURNAMENT_PROMPT`, and `PATCH_TOURNAMENT_WORKSPACE`.

## Hidden evidence

An approved hidden reproduction can be copied only into preflight and grader snapshots:

```toml
[[overlays]]
kind = "approved-hidden"
source = "private/test_bug.py"
destination = "tests/test_bug.py"
```

Overlay destinations may not be absolute, escape the workspace, or overwrite a tracked file.

## Trust and safety boundary

- The source is a committed Git ref; uncommitted and untracked source changes are intentionally excluded.
- Version 1 is report-only and refuses to overwrite an existing output directory.
- Commands are always executed as argument arrays, never through a shell.
- The Codex adapter requests a workspace-write sandbox. The generic command adapter is **not an OS sandbox** and must run only trusted executables; use a container or CI isolation for untrusted agents.
- Checks and candidate code may execute arbitrary repository code. Run tournaments with the same caution as a normal build or test job.
- Symlinks in the selected snapshot are rejected when they point outside the snapshot.

See [`examples/tournament.toml.example`](examples/tournament.toml.example) for the complete configuration shape.

A self-contained live Codex smoke fixture is available under [`examples/codex-smoke`](examples/codex-smoke). Copy it to a temporary directory, initialize `repo/` as a Git repository, and run its `tournament.toml` to exercise three parallel candidates.
