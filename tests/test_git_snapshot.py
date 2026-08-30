from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from patch_tournament.git_snapshot import capture_inspection, create_snapshot
from tests.helpers import init_repo, run


class GitSnapshotTests(unittest.TestCase):
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
