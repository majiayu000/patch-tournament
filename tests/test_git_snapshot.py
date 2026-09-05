from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from patch_tournament.git_snapshot import capture_inspection, create_snapshot
from tests.helpers import init_repo, run


class GitSnapshotTests(unittest.TestCase):
    def test_snapshot_preserves_blobs_modes_links_and_ignored_tracked_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            init_repo(source, {
                ".gitattributes": "hidden.txt export-ignore\nversion.txt export-subst\n",
                "hidden.txt": "keep\n", "version.txt": "$Format:%H$\n",
                "run.sh": "#!/bin/sh\nexit 0\n",
            })
            (source / ".gitignore").write_text("hidden.txt\n")
            (source / "binary.dat").write_bytes(b"\x00\xff\x01")
            (source / "run.sh").chmod(0o755)
            (source / "link").symlink_to("hidden.txt")
            self.assertEqual(run(["git", "add", "-A"], source).returncode, 0)
            self.assertEqual(run(["git", "commit", "-m", "fixture"], source).returncode, 0)
            destination = root / "snapshot"
            create_snapshot(source, "HEAD", destination)
            self.assertEqual((destination / "hidden.txt").read_text(), "keep\n")
            self.assertEqual((destination / "version.txt").read_text(), "$Format:%H$\n")
            self.assertEqual((destination / "binary.dat").read_bytes(), b"\x00\xff\x01")
            self.assertTrue((destination / "run.sh").stat().st_mode & 0o111)
            self.assertTrue((destination / "link").is_symlink())
            self.assertIn("hidden.txt", run(["git", "ls-files"], destination).stdout)
            self.assertEqual(capture_inspection(destination).changed_files, ())

    def test_snapshot_rejects_links_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            init_repo(source, {"app.py": "VALUE = 1\n"})
            (source / "escape").symlink_to("../outside")
            self.assertEqual(run(["git", "add", "escape"], source).returncode, 0)
            self.assertEqual(run(["git", "commit", "-m", "link"], source).returncode, 0)
            with self.assertRaisesRegex(RuntimeError, "link escapes"):
                create_snapshot(source, "HEAD", root / "snapshot")

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
