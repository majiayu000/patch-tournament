from __future__ import annotations

import unittest

from patch_tournament.git_snapshot import GitInspection
from patch_tournament.guard import evaluate_guard


def inspection(
    files: tuple[str, ...],
    *,
    line_stats: dict[str, dict[str, int | None]] | None = None,
    statuses: dict[str, str] | None = None,
) -> GitInspection:
    return GitInspection(
        changed_files=files,
        line_stats=line_stats
        or {path: {"added": 5, "deleted": 0} for path in files},
        patch="",
        statuses=statuses or {path: "M" for path in files},
    )


class GuardTests(unittest.TestCase):
    def test_reports_observed_diff_facts_without_semantic_verdict(self) -> None:
        result = evaluate_guard(
            inspection(
                ("added.py", "changed.py", "deleted.py"),
                statuses={"added.py": "A", "changed.py": "M", "deleted.py": "D"},
            )
        )

        self.assertEqual(result.status, "observed")
        self.assertEqual(result.violations, ())
        self.assertEqual(result.facts.changed_files, ("added.py", "changed.py", "deleted.py"))
        self.assertEqual(result.facts.added_files, ("added.py",))
        self.assertEqual(result.facts.modified_files, ("changed.py",))
        self.assertEqual(result.facts.deleted_files, ("deleted.py",))
        self.assertEqual(result.facts.total_file_count, 3)
        self.assertEqual(result.facts.text_changed_lines, 15)
        self.assertTrue(result.facts.line_count_complete)

    def test_empty_diff_is_reported_as_empty_not_passed(self) -> None:
        result = evaluate_guard(inspection(()))

        self.assertEqual(result.status, "empty")
        self.assertEqual(result.facts.total_file_count, 0)

    def test_only_explicit_protected_paths_create_a_violation(self) -> None:
        result = evaluate_guard(
            inspection(("src/app.py", ".github/workflows/release.yml")),
            protected_paths=(".github/**",),
        )

        self.assertEqual(result.status, "constraint_violation")
        self.assertEqual(len(result.violations), 1)
        self.assertEqual(result.violations[0].code, "protected_path_changed")
        self.assertEqual(result.violations[0].paths, (".github/workflows/release.yml",))

    def test_large_patch_remains_an_observation_without_an_explicit_constraint(self) -> None:
        files = tuple(f"src/module_{index}.py" for index in range(20))

        result = evaluate_guard(inspection(files))

        self.assertEqual(result.status, "observed")
        self.assertEqual(result.violations, ())
        self.assertEqual(result.facts.total_file_count, 20)

    def test_binary_diff_does_not_claim_a_complete_text_line_count(self) -> None:
        result = evaluate_guard(
            inspection(
                ("asset.bin", "app.py"),
                line_stats={
                    "asset.bin": {"added": None, "deleted": None},
                    "app.py": {"added": 2, "deleted": 1},
                },
            )
        )

        self.assertEqual(result.facts.binary_files, ("asset.bin",))
        self.assertIsNone(result.facts.text_changed_lines)
        self.assertFalse(result.facts.line_count_complete)


if __name__ == "__main__":
    unittest.main()
