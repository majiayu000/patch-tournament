---
name: patch-guard
description: Record a task-start Git worktree snapshot and report exactly which changes a coding agent made. Use for implementation tasks when task-level change attribution matters, especially in a dirty worktree or when the user asks to avoid unrelated scope. Do not use for read-only work or as a replacement for project tests.
---

# Patch Guard

Use the existing primary Codex session. Patch Guard is a deterministic task-diff recorder,
not a semantic judge, acceptance-contract generator, or second model.

## Workflow

1. Before editing any task file, identify the repository root and choose a new snapshot path
   outside the worktree or under `<repo>/.git/patch-tournament/`. Do not overwrite an old
   snapshot.
2. Create the parent directory, then capture the task-start state:

   ```bash
   patch-tournament snapshot --repo <repo> --output <new-snapshot-path> --format json
   ```

   If `patch-tournament` is unavailable, try `python3 -m patch_tournament`. If neither works,
   report that task-level attribution is unavailable; do not manufacture a baseline later.
3. Implement the user's request normally. Follow the nearest repository instructions and run
   fresh, focused project verification.
4. After verification, inspect only changes made since the saved snapshot:

   ```bash
   patch-tournament guard --repo <repo> --snapshot <snapshot-path> --format json
   ```

   Add `--protect <path-or-glob>` only when that boundary was explicitly established by the
   user or repository instructions.
5. Interpret the result conservatively:
   - `observed`: facts were collected. Trace every changed file to the request and mention any
     scope that cannot be justified. Do not call this a pass.
   - `empty`: no task-owned diff exists. If implementation was expected, do not claim it was
     completed.
   - `constraint_violation`: do not claim completion. Revert only task-owned changes that
     truly violate the explicit boundary, or explain the conflict and request direction when
     the requested behavior requires that path.
   - `error`: report the error clearly. Do not silently fall back to a `HEAD` diff and present
     it as task attribution.

## Boundaries

- The report says what changed, not whether the design is good or the behavior is correct.
- Do not impose universal file-count or line-count budgets. A large necessary patch can be
  valid; a one-line speculative patch can be wrong.
- Do not classify filenames as production, tests, dependencies, or documentation to infer
  scope. Use repository facts and the request.
- Do not create an automatic simplify/retry loop in response to the report.
- Never weaken tests or delete required behavior merely to reduce the diff.
- Preserve all changes that predate the snapshot, including overlapping dirty files.
- If the snapshot was not taken before implementation, state that reliable task attribution
  is unavailable. A retrospective snapshot does not repair the missing evidence.
- Do not launch Patch Tournament automatically. It creates additional model sessions and
  spends more tokens. Use it only when the user requested candidate comparison or explicitly
  approved that escalation.
- Never auto-apply a tournament winner or perform unrelated external writes.
