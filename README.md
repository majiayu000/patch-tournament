# Patch Tournament

Patch Tournament gives coding agents an exact answer to a narrow question: **what changed
during this task?** It records the Git worktree before implementation, compares that state
with the final worktree, and emits deterministic facts. It does not decide whether a patch is
well designed, invent a task contract, or call another model.

The default workflow is deliberately small:

```text
task-start snapshot -> one coding agent -> project tests -> task-diff facts
```

This design and the J-Space failure pattern that motivated it are documented in
[`DESIGN.md`](DESIGN.md).

## Agent workflow

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

## Install for Codex

Requirements are Python 3.11+ and Git.

```bash
git clone https://github.com/majiayu000/patch-tournament.git
cd patch-tournament
python3 -m pip install -e .
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/patch-guard" ~/.codex/skills/patch-guard
```

The included [`patch-guard` skill](skills/patch-guard/SKILL.md) is written for an agent, not
for an end user operating an interactive dashboard. It tells Codex to take the snapshot at
task start and interpret the final report conservatively. Invoke it with `$patch-guard` when
you want task-level change attribution.

## Optional tournament mode

The original multi-agent tournament remains an explicit, costly tool for evaluations or
cases where the user asks to compare independent candidates:

```bash
cp examples/tournament.toml.example tournament.toml
patch-tournament run --config tournament.toml --output /tmp/tournament-result
```

It runs candidates in isolated Git snapshots, applies their patches to fresh grader
snapshots, gates them using independently supplied checks, and reports the smallest passing
candidate. It never auto-applies the winner. Existing, reproduction, and approved-hidden
checks may gate selection; agent-authored speculative checks may not.

Tournament mode spends additional tokens and is never launched automatically by Patch
Guard. See [`examples/tournament.toml.example`](examples/tournament.toml.example) for its
configuration.

## Limits and safety

- Task-diff facts do not prove behavioral correctness; use the repository's tests and the
  user's acceptance evidence.
- A protected glob is caller policy, not an inferred semantic rule.
- Commands are executed as argument arrays rather than shell strings.
- The generic tournament command adapter is not an OS sandbox; run only trusted executables.
- Checks and candidate code may execute repository code and should be treated like a normal
  build job.
- Binary changes are reported with incomplete text-line counts rather than fake numbers.

Run the test suite with:

```bash
PYTHONPATH=src python3 -m unittest discover -v
```
