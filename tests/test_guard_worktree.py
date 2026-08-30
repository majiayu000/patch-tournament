from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from patch_tournament.git_snapshot import (
    capture_task_inspection,
    capture_worktree_inspection,
    create_worktree_snapshot,
    read_worktree_snapshot,
    write_worktree_snapshot,
)
from tests.helpers import init_repo, run


class GuardWorktreeTests(unittest.TestCase):
    def test_task_inspection_preserves_unicode_git_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            init_repo(repo, {"中文.py": "VALUE = 1\n"})
            (repo / "中文.py").write_text("VALUE = 2\n", encoding="utf-8")
            snapshot = create_worktree_snapshot(repo)

            (repo / "中文.py").write_text("VALUE = 3\n", encoding="utf-8")
            result = capture_task_inspection(repo, snapshot)

            self.assertEqual(result.changed_files, ("中文.py",))
            self.assertEqual(result.statuses, {"中文.py": "M"})

    def test_task_inspection_uses_snapshot_state_for_each_file_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            init_repo(repo, {"app.py": "VALUE = 1\n"})
            (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
            (repo / "empty.txt").touch()
            (repo / "old.txt").write_text("old\n", encoding="utf-8")
            snapshot = create_worktree_snapshot(repo)

            (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            (repo / "empty.txt").write_text("now populated\n", encoding="utf-8")
            (repo / "old.txt").unlink()
            (repo / "new.txt").write_text("new\n", encoding="utf-8")
            result = capture_task_inspection(repo, snapshot)

            self.assertEqual(
                result.changed_files,
                ("app.py", "empty.txt", "new.txt", "old.txt"),
            )
            self.assertEqual(result.statuses, {
                "app.py": "M",
                "empty.txt": "M",
                "new.txt": "A",
                "old.txt": "D",
            })

    def test_task_inspection_excludes_changes_that_predate_the_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            init_repo(repo, {"app.py": "VALUE = 1\n"})
            (repo / "legacy.py").write_text("LEGACY = True\n", encoding="utf-8")
            snapshot = create_worktree_snapshot(repo)

            (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
            result = capture_task_inspection(repo, snapshot)

            self.assertEqual(result.changed_files, ("app.py",))
            self.assertEqual(result.statuses, {"app.py": "M"})

    def test_captures_tracked_and_untracked_without_mutating_index(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            init_repo(repo, {"app.py": "VALUE = 1\n"})
            (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
            (repo / "new.py").write_text("NEW = True\n", encoding="utf-8")
            before = run(["git", "status", "--porcelain=v1"], repo).stdout

            result = capture_worktree_inspection(repo, "HEAD")

            after = run(["git", "status", "--porcelain=v1"], repo).stdout
            self.assertEqual(after, before)
            self.assertEqual(result.changed_files, ("app.py", "new.py"))
            self.assertEqual(result.statuses, {"app.py": "M", "new.py": "A"})
            self.assertIn("diff --git a/app.py b/app.py", result.patch)
            self.assertIn("diff --git a/new.py b/new.py", result.patch)

    def test_snapshot_file_round_trips_and_cannot_be_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            output = Path(raw) / "snapshot.json"
            init_repo(repo, {"app.py": "VALUE = 1\n"})
            (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
            snapshot = create_worktree_snapshot(repo)

            write_worktree_snapshot(snapshot, output)

            self.assertEqual(read_worktree_snapshot(output), snapshot)
            with self.assertRaises(FileExistsError):
                write_worktree_snapshot(snapshot, output)

    def test_snapshot_cannot_be_used_for_another_repository(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            first = Path(raw) / "first"
            second = Path(raw) / "second"
            init_repo(first, {"app.py": "VALUE = 1\n"})
            init_repo(second, {"app.py": "VALUE = 1\n"})
            snapshot = create_worktree_snapshot(first)

            with self.assertRaisesRegex(RuntimeError, "snapshot belongs to"):
                capture_task_inspection(second, snapshot)


if __name__ == "__main__":
    unittest.main()
