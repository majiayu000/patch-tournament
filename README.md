# Patch Tournament

Patch Tournament runs three independent coding agents against the same task, verifies every
patch in a fresh grader workspace, and ranks candidates that pass caller-supplied checks.
It lets you compare patch scope across alternatives. A smaller passing patch is not proof
of better design or complete behavioral correctness.

The primary workflow is:

```text
task evidence -> three isolated candidates -> independent checks -> smallest passing patch
```

The included Patch Guard remains available as a lower-cost companion when only task-level diff
attribution is needed. Neither mode can replace project tests or semantic review. The design
boundaries are documented in
[`DESIGN.md`](https://github.com/majiayu000/patch-tournament/blob/main/DESIGN.md).

## Install

Patch Tournament requires Python 3.11+ and Git. Install the CLI in an isolated tool
environment from the repository with `uv` or `pipx`:

```bash
uv tool install 'git+https://github.com/majiayu000/patch-tournament.git'
# or: pipx install 'git+https://github.com/majiayu000/patch-tournament.git'
```

Verify the installation:

```bash
patch-tournament --version
```

Version `0.3.0a1` is also available as a wheel and source distribution on
[GitHub Releases](https://github.com/majiayu000/patch-tournament/releases/tag/v0.3.0a1).
PyPI publication is currently blocked on Trusted Publisher configuration; do not use the
bare PyPI package name until that is resolved.

## Three-agent workflow

From a repository checkout, start from the provided configuration:

```bash
cp examples/tournament.toml.example tournament.toml
```

Set the repository, task evidence, and project-owned checks in `tournament.toml`, then run:

```bash
patch-tournament run --config tournament.toml --output /tmp/tournament-result
```

The example already uses three concurrent Codex candidates. Grader overlays are not copied
into candidate workspaces. Tournament applies each patch to a fresh grader, rejects candidates
that fail gating checks, and writes `report.json`, `report.md`, every candidate patch, and
`winner.patch`. It never applies the winner automatically.

Every gating check (`existing`, `reproduction`, or `approved-hidden`) must declare non-empty
`evidence_paths`: exact, workspace-relative file paths for its test scripts, fixtures, helpers,
and test configuration. They must exist in the selected Git revision or be supplied by an
overlay. Symlinked evidence is rejected. Candidates that change these files are ineligible.
For example:

```toml
[[checks]]
id = "regression"
kind = "reproduction"
command = ["python3", "-B", "tests/test_regression.py"]
evidence_paths = ["tests/test_regression.py", "tests/helpers.py"]
baseline = "fail"
timeout_seconds = 60
```

Include every file controlling the check; the tool does not infer command dependencies.
Use fixed test modules for gates: discovery commands can also collect candidate-authored
tests, so they do not isolate your original acceptance set.
At least one gating check is required. Speculative-only configurations are errors.
This is a breaking configuration change from 0.2.0.

## Lightweight Patch Guard workflow

Create a snapshot before the agent edits anything. Store it outside the worktree or under
`.git/` so the snapshot file itself cannot appear in the task diff.

```bash
mkdir -p .git/patch-tournament
patch-tournament snapshot \
  --repo . \
  --output .git/patch-tournament/task-123.json \
  --format json
```

After implementing the request and running the repository's own verification:

```bash
patch-tournament guard \
  --repo . \
  --snapshot .git/patch-tournament/task-123.json \
  --format json
```

The result uses schema version 2 and contains file statuses, per-file line statistics,
binary-file markers, and aggregate counts. It has three non-error statuses:

| Status | Exit | Meaning |
|---|---:|---|
| `observed` | 0 | Task changes were measured. This is not a correctness verdict. |
| `empty` | 0 | No task-owned change was found. This is not a pass. |
| `constraint_violation` | 3 | A path explicitly protected by the caller changed. |
| `error` | 1 | The snapshot, repository, or Git operation was invalid. |

Only an explicit boundary can produce a violation:

```bash
patch-tournament guard \
  --repo . \
  --snapshot .git/patch-tournament/task-123.json \
  --protect '.github/**' \
  --format json
```

There are no built-in file budgets, task profiles, production/test classifiers, dependency
exceptions, or automatic retry loops. The agent must use the user's request, repository
instructions, and project tests to decide whether each reported file is justified.

## Why the start snapshot matters

Diffing against `HEAD` alone mixes the user's pre-existing dirty changes with the agent's
work. Patch Tournament stores the complete task-start worktree delta and reconstructs that
state during review. It can therefore isolate later edits even when the same repository was
already dirty.

If no task-start snapshot exists, do not create one after implementation and claim that it
proves scope. The attribution evidence no longer exists.

## Install the Codex plugin

The Python package installs the CLI. To let Codex record the task baseline and report the
task-owned diff automatically, install the repository's `patch-guard` plugin:

```bash
codex plugin marketplace add majiayu000/patch-tournament
codex plugin add patch-guard@patch-tournament
```

Start a new Codex session after installation. The plugin runs automatically for coding turns;
you do not need to invoke `$patch-guard`. Do not keep the older manually linked `patch-guard`
skill enabled at the same time, because that would duplicate the workflow.

## Why three candidates

Three candidates are the example configuration, not an empirically established optimum.
Acceptance comes from caller-supplied checks; size only ranks candidates that already passed.
Ranking prefers fewer dependency manifest changes, then fewer production files, fewer
production changed lines, fewer total files, and fewer total changed lines, in that order.
It is not a semantic complexity score. Existing, reproduction, and approved-hidden checks may gate
selection, while agent-authored speculative checks may not. See
[`examples/tournament.toml.example`](https://github.com/majiayu000/patch-tournament/blob/main/examples/tournament.toml.example)
for the complete configuration.

The [recorded historical-task comparison](PROJECT_STATUS.md) includes correctness checks,
patch review, token usage, and elapsed time. It does not establish a general cost or quality win.

## Limits and safety

- Task-diff facts do not prove behavioral correctness; use the repository's tests and the
  user's acceptance evidence.
- A protected glob is caller policy, not an inferred semantic rule.
- Commands are executed as argument arrays rather than shell strings.
- The generic tournament command adapter is not an OS sandbox; run only trusted executables.
- Workspaces share the host and inherit its environment. Hidden evidence is not a security
  boundary against a process that can read the host filesystem. Declare all verifier inputs;
  evidence-path protection does not sandbox candidate code executed during a check.
- Checks and candidate code may execute repository code and should be treated like a normal
  build job.
- Guard reports incomplete text-line counts for binary files. Tournament currently assigns
  each unknown added/deleted line count a ranking penalty of 1,000,000.
- Python candidates receive `PYTHONDONTWRITEBYTECODE=1`; explicit bytecode compilation and
  other build outputs still need project-owned ignore rules.
- Snapshots preserve committed blobs, including `export-ignore` and `export-subst` files.
  Submodules and links escaping the snapshot are rejected explicitly.
- Guard measures changes between two instants; concurrent writers in the same worktree
  cannot be distinguished. Snapshot JSON includes uncommitted file contents; store it privately.

Run the test suite with:

```bash
PYTHONPATH=src python3 -m unittest discover -v
```
