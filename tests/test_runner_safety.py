from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from patch_tournament.runner import TournamentError, run_tournament
from tests.helpers import init_repo, run


def write_fixture(root: Path, *, expected_baseline: str = "fail") -> Path:
    repo = root / "repo"
    init_repo(repo, {
        "value.py": "VALUE = 1\n",
        "agent.py": "from pathlib import Path\nPath('pyproject.toml').write_text('[project]\\nname=\"extra\"\\n')\n",
    })
    (root / "issue.md").write_text("Make VALUE equal two.\n", encoding="utf-8")
    (root / "test_hidden.py").write_text(
        "import unittest\nfrom value import VALUE\n\n"
        "class ValueTests(unittest.TestCase):\n"
        "    def test_value(self): self.assertEqual(VALUE, 2)\n",
        encoding="utf-8",
    )
    config = root / "tournament.toml"
    config.write_text(
        "version=1\n[project]\nrepo=\"repo\"\nref=\"HEAD\"\n"
        "[[sources]]\nkind=\"issue\"\npath=\"issue.md\"\nvisible=true\n"
        "[candidates]\nadapter=\"command\"\ncommand=[\"python3\",\"agent.py\"]\n"
        "count=1\nconcurrency=1\ntimeout_seconds=10\n"
        "[[checks]]\nid=\"regression\"\nkind=\"approved-hidden\"\n"
        "evidence_paths=[\"test_hidden.py\"]\n"
        "command=[\"python3\",\"-m\",\"unittest\",\"test_hidden.py\"]\n"
        f"baseline=\"{expected_baseline}\"\ntimeout_seconds=10\n"
        "[[overlays]]\nkind=\"approved-hidden\"\nsource=\"test_hidden.py\"\n"
        "destination=\"test_hidden.py\"\n"
        "[safety]\nreport_only=true\nprotected_paths=[\"pyproject.toml\"]\n",
        encoding="utf-8",
    )
    return config


class RunnerSafetyTests(unittest.TestCase):
    def test_missing_evidence_aborts_before_generating_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = write_fixture(root)
            config.write_text(config.read_text().replace(
                'evidence_paths=["test_hidden.py"]', 'evidence_paths=["missing.py"]',
            ))
            with self.assertRaisesRegex(TournamentError, "evidence must be a regular file"):
                run_tournament(config, root / "output")
            self.assertFalse((root / "output").exists())

    def test_candidate_cannot_replace_an_overlay_parent_with_a_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = write_fixture(root)
            config.write_text(config.read_text().replace(
                'evidence_paths=["test_hidden.py"]', 'evidence_paths=["private/test_hidden.py"]',
            ).replace(
                'destination="test_hidden.py"', 'destination="private/test_hidden.py"',
            ).replace(
                '"test_hidden.py"]', '"private/test_hidden.py"]',
            ))
            repo = root / "repo"
            (repo / "agent.py").write_text(
                "from pathlib import Path\nPath('private').symlink_to('../outside')\n",
            )
            self.assertEqual(run(["git", "add", "agent.py"], repo).returncode, 0)
            self.assertEqual(run(["git", "commit", "-m", "candidate fixture"], repo).returncode, 0)
            result = run_tournament(config, root / "output")
            report = json.loads(result.report_path.read_text())
            self.assertEqual(result.status, "no_winner")
            self.assertIn("protected_path:private", report["candidates"]["c01"]["failures"])

    def test_output_inside_source_repository_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = write_fixture(root)

            with self.assertRaisesRegex(TournamentError, "outside the source repository"):
                run_tournament(config, root / "repo" / "tournament-output")

    def test_protected_path_change_produces_no_winner(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result = run_tournament(write_fixture(root), root / "output")
            report = json.loads(result.report_path.read_text(encoding="utf-8"))

            self.assertEqual(result.status, "no_winner")
            self.assertIn("protected_path:pyproject.toml", report["candidates"]["c01"]["failures"])
            self.assertFalse((root / "output" / "winner.patch").exists())

    def test_baseline_mismatch_aborts_before_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            output = root / "output"

            with self.assertRaisesRegex(TournamentError, "baseline preflight failed"):
                run_tournament(write_fixture(root, expected_baseline="pass"), output)

            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
