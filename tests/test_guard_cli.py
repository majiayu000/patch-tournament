from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from patch_tournament.cli import main
from tests.helpers import init_repo


class GuardCliTests(unittest.TestCase):
    def _snapshot(self, repo: Path, path: Path) -> dict[str, object]:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main([
                "snapshot", "--repo", str(repo), "--output", str(path),
                "--format", "json",
            ])
        self.assertEqual(exit_code, 0)
        self.assertTrue(path.is_file())
        return json.loads(stdout.getvalue())

    def test_snapshot_then_guard_reports_only_changes_made_after_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            snapshot_path = Path(raw) / "task-snapshot.json"
            init_repo(repo, {"app.py": "VALUE = 1\n"})
            (repo / "legacy.py").write_text("LEGACY = True\n", encoding="utf-8")

            created = self._snapshot(repo, snapshot_path)
            (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main([
                    "guard", "--repo", str(repo), "--snapshot", str(snapshot_path),
                    "--format", "json",
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(created["schema_version"], 2)
            self.assertEqual(created["status"], "snapshot_created")
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["status"], "observed")
            self.assertEqual(payload["facts"]["changed_files"], ["app.py"])
            self.assertNotIn("verdict", payload)
            self.assertNotIn("suggested_action", payload)

    def test_no_task_change_is_empty_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            snapshot_path = Path(raw) / "task-snapshot.json"
            init_repo(repo, {"app.py": "VALUE = 1\n"})
            self._snapshot(repo, snapshot_path)
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main([
                    "guard", "--repo", str(repo), "--snapshot", str(snapshot_path),
                    "--format", "json",
                ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "empty")

    def test_explicit_protected_path_violation_uses_exit_code_three(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            snapshot_path = Path(raw) / "task-snapshot.json"
            init_repo(repo, {"pyproject.toml": "[project]\nname='demo'\n"})
            self._snapshot(repo, snapshot_path)
            (repo / "pyproject.toml").write_text(
                "[project]\nname='changed'\n", encoding="utf-8"
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main([
                    "guard", "--repo", str(repo), "--snapshot", str(snapshot_path),
                    "--protect", "pyproject.toml", "--format", "json",
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 3)
            self.assertEqual(payload["status"], "constraint_violation")

    def test_malformed_snapshot_is_a_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw) / "repo"
            snapshot_path = Path(raw) / "broken.json"
            init_repo(repo, {"app.py": "VALUE = 1\n"})
            snapshot_path.write_text("not json", encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main([
                    "guard", "--repo", str(repo), "--snapshot", str(snapshot_path),
                    "--format", "json",
                ])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["status"], "error")
            self.assertTrue(payload["error"])


if __name__ == "__main__":
    unittest.main()
