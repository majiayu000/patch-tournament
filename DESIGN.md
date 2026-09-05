# Design constraints

Status: three-candidate primary workflow with a factual Guard companion, 2026-09-05.

## Purpose

Patch Tournament must not become a universal judge of whether one code change is
over-designed. It compares alternatives, rejecting candidates that fail caller-supplied
evidence, and ranking only the survivors by patch surface. This is a relative
selection claim, not a semantic verdict that the winner is ideally designed.

The primary product is an explicitly invoked three-candidate Tournament. Patch Guard remains a
lower-cost companion that reports task-owned changes without calling another model.

## J-Space warning case

The design was checked against `majiayu000/dsh-plugin-j-space` as a concrete complexity
warning case. At the inspected fork revision `0e12a72`:

- the skill surface contains 13 Markdown documents, about 3,300 lines and roughly 47,000
  tokens if loaded in full;
- the entry skill routes among nine modules, while the plugin exposes four runtime modes and
  a separate 657-line ledger controller;
- the mode API stores, reads, displays, and logs a selected mode, but the fork's runtime does
  not connect that mode to prompt or skill activation;
- commit `5a055d0` deleted the controller's tests to keep the repository "clean and lean";
- the next upstream runtime repair adds about 170 lines of integration and declares an npm
  test command whose referenced test file is absent from that revision.

These facts do not prove that every J-Space mechanism is wrong. They show a failure pattern:
semantic behavior was represented by modes, routing tables, thresholds, markers, and
configuration faster than the execution and verification paths could remain aligned. Each
compatibility repair then enlarged the surface that future repairs had to understand.

Patch Tournament is already exposed to the same pattern. Fixing every false positive by
adding another test glob, manifest name, language rule, scope profile, threshold, exception,
or operating mode would reproduce it.

## Hard boundaries

1. **Facts, not semantic verdicts.** Built-in logic may report files, statuses, line counts,
   command results, and task-start versus task-end differences. It must not claim that a
   generic patch is correct, excessive, or complete.
2. **Only explicit constraints block.** A protected path or forbidden operation may block
   only when it came from the user or applicable repository policy. Built-in size heuristics
   are never gates.
3. **No universal scope budgets.** File-count, line-count, and new-file thresholds may be
   shown as caller-supplied policy, but the package must not present universal `local`,
   `standard`, or `broad` numbers as truth.
4. **No false success.** An empty diff, incomplete inspection, or failed command is reported
   as its exact state. It is not converted into `pass` or `complete`.
5. **One primary path.** The supported primary workflow remains three isolated candidates,
   fresh graders, independent checks, deterministic selection, and report-only output.
   Additional modes require a demonstrated use case and an end-to-end test.
6. **Declaration must reach execution.** Every option, mode, configuration field, and
   suggested action needs a tested runtime consumer. A setting that is only stored, rendered,
   or documented is not a feature.
7. **Do not repair heuristics with growing exception tables.** When a generic classifier is
   repeatedly wrong, remove or demote the judgment instead of adding an open-ended list of
   special cases.
8. **Agent feedback stays bounded.** Reports describe observations and explicit violations.
   They do not instruct the agent to simplify, refactor, add wrappers, or remove necessary
   behavior merely to satisfy a metric.
9. **Model calls stay explicit.** Starting a Tournament requires a direct user or caller
   invocation. Stop hooks never launch candidates, and winners are never applied automatically.

## Consequences implemented in 0.2

The Guard-first draft was reduced accordingly:

- replace the profile-driven `pass/review/block` judgment with a task-start snapshot and a
  factual diff result;
- reserve constraint violations for caller-supplied protected boundaries;
- report an empty patch as `empty`, not `pass`;
- treat manifest and test classification as descriptive, fallible metadata rather than a
  correctness or scope decision;
- keep the existing tournament engine behind explicit approval and outside the default flow;
- evaluate the resulting workflow on real historical tasks before adding another mode or
  policy surface.

The preferred response to uncertainty is a smaller claim, not a larger framework.

## Current direction

The 0.2 factual Guard remains supported, but it is no longer the repository's primary product
story. The main workflow is the original three-candidate Tournament because it can compare
multiple correct implementations without pretending that a fixed line or file budget is a
universal design rule. Patch Guard remains useful for low-cost attribution and explicit protected
paths.

## Acceptance evidence integrity

Every gating check declares its workspace-relative `evidence_paths`. The baseline verifies
that these are regular files, and candidate patches touching them are rejected before grading.
Overlay destinations are protected as well. At least one gating check is required; speculative
checks alone cannot establish eligibility. The caller owns the complete list of test scripts,
fixtures, helpers, and configuration. This does not sandbox executed code or discover omitted
dependencies, and a passing report remains subject to semantic review.

Snapshots read committed Git blobs directly instead of using release archives, so export
attributes cannot omit or substitute task-start files. Renames are represented consistently
as deletion plus addition in Tournament artifacts and size statistics.
