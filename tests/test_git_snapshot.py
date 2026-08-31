from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from patch_tournament.git_snapshot import capture_inspection, create_snapshot
from tests.helpers import init_repo, run


class GitSnapshotTests(unittest.TestCase):
    def test_snapshot_ignores_inherited_commit_signing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            init_repo(source, {"app.py": "VALUE = 1\n"})
            global_config = root / "gitconfig"
            global_config.write_text(
                "[commit]\n\tgpgSign = true\n[gpg]\n\tprogram = /bin/false\n",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"GIT_CONFIG_GLOBAL": str(global_config)}):
                snapshot_head = create_snapshot(source, "HEAD", root / "snapshot")

            self.assertTrue(snapshot_head)

    def test_snapshot_supports_a_committed_empty_tree(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            run(["git", "init", "--quiet"], source)
            run(["git", "config", "user.name", "Patch Tournament Tests"], source)
            run(["git", "config", "user.email", "tests@example.invalid"], source)
            result = run(
                ["git", "commit", "--allow-empty", "--quiet", "-m", "baseline"],
                source,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            snapshot = root / "snapshot"
            snapshot_head = create_snapshot(source, "HEAD", snapshot)

            self.assertTrue(snapshot_head)
            self.assertEqual(run(["git", "ls-files"], snapshot).stdout, "")

    def test_snapshot_and_diff_include_committed_and_untracked_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            baseline = init_repo(source, {"app.py": "VALUE = 1\n"})
            snapshot = root / "snapshot"

            snapshot_head = create_snapshot(source, "HEAD", snapshot)
            (snapshot / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
            run(["git", "add", "app.py"], snapshot)
            run(["git", "commit", "--quiet", "-m", "agent committed"], snapshot)
            (snapshot / "new.py").write_text("NEW = True\n", encoding="utf-8")

            inspection = capture_inspection(snapshot)

            self.assertNotEqual(snapshot_head, baseline)
            self.assertEqual(inspection.changed_files, ("app.py", "new.py"))
            self.assertIn("diff --git a/app.py b/app.py", inspection.patch)
            self.assertIn("diff --git a/new.py b/new.py", inspection.patch)
            self.assertEqual((source / "app.py").read_text(), "VALUE = 1\n")


if __name__ == "__main__":
    unittest.main()
