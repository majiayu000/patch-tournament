from __future__ import annotations

import unittest

from patch_tournament.selection import CandidateEvaluation, inspect_metrics, select_winner


def candidate(
    candidate_id: str,
    *,
    correct: bool,
    production_lines: int,
    dependency: bool = False,
) -> CandidateEvaluation:
    files = ["src/main.py", "tests/test_main.py"]
    stats = {
        "src/main.py": {"added": production_lines, "deleted": 0},
        "tests/test_main.py": {"added": 5, "deleted": 0},
    }
    if dependency:
        files.append("pyproject.toml")
        stats["pyproject.toml"] = {"added": 1, "deleted": 0}
    metrics = inspect_metrics(
        files,
        stats,
        test_globs=("tests/**",),
        dependency_manifests=("pyproject.toml",),
    )
    return CandidateEvaluation(
        candidate_id=candidate_id,
        correct=correct,
        failures=() if correct else ("verification",),
        metrics=metrics,
    )


class SelectionTests(unittest.TestCase):
    def test_selects_smallest_correct_candidate(self) -> None:
        selection = select_winner(
            [
                candidate("large", correct=True, production_lines=40),
                candidate("small", correct=True, production_lines=8),
                candidate("broken", correct=False, production_lines=1),
            ]
        )

        self.assertEqual(selection.winner_id, "small")
        self.assertEqual(selection.eligible_count, 2)

    def test_dependency_change_loses_before_line_count(self) -> None:
        selection = select_winner(
            [
                candidate("dependency", correct=True, production_lines=1, dependency=True),
                candidate("no-dependency", correct=True, production_lines=9),
            ]
        )

        self.assertEqual(selection.winner_id, "no-dependency")

    def test_returns_no_winner_when_all_candidates_fail(self) -> None:
        selection = select_winner([candidate("broken", correct=False, production_lines=1)])

        self.assertIsNone(selection.winner_id)
        self.assertEqual(selection.status, "no_winner")

    def test_test_files_do_not_count_as_production(self) -> None:
        metrics = inspect_metrics(
            ["src/main.py", "tests/test_main.py", "src/main_test.py"],
            {
                "src/main.py": {"added": 4, "deleted": 1},
                "tests/test_main.py": {"added": 100, "deleted": 0},
                "src/main_test.py": {"added": 50, "deleted": 0},
            },
            test_globs=("tests/**", "**/*_test.py"),
            dependency_manifests=(),
        )

        self.assertEqual(metrics.production_files, ("src/main.py",))
        self.assertEqual(metrics.production_changed_lines, 5)
        self.assertEqual(metrics.total_changed_lines, 155)
