from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from patch_tournament.runner import run_tournament
from tests.helpers import init_repo


class TournamentEndToEndTests(unittest.TestCase):
    def test_test_tampering_loses_to_verified_patch_with_rename(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            test_source = "from value import VALUE\nassert VALUE == 2\n"
            init_repo(repo, {
                "value.py": "VALUE = 1\n",
                "test_value.py": test_source,
                "old.txt": "one\ntwo\nthree\n",
                "agent.py": (
                    "import os\nfrom pathlib import Path\n"
                    "if os.environ['PATCH_TOURNAMENT_CANDIDATE_ID'] == 'c01':\n"
                    "    Path('test_value.py').write_text('pass\\n')\n"
                    "else:\n"
                    "    Path('value.py').write_text('VALUE = 2\\n')\n"
                    "    Path('old.txt').rename('new.txt')\n"
                ),
            })
            (root / "issue.md").write_text("Make VALUE equal two and rename old.txt to new.txt.\n")
            config = root / "tournament.toml"
            config.write_text('''version=1
[project]
repo="repo"
ref="HEAD"
[[sources]]
kind="issue"
path="issue.md"
visible=true
[candidates]
adapter="command"
command=["python3", "agent.py"]
count=2
concurrency=2
timeout_seconds=20
[[checks]]
id="regression"
kind="reproduction"
command=["python3", "-B", "test_value.py"]
evidence_paths=["./test_value.py"]
baseline="fail"
timeout_seconds=20
[selection]
test_globs=["test_*.py"]
[safety]
report_only=true
''')
            result = run_tournament(config, root / "output")
            report = json.loads(result.report_path.read_text())
            self.assertEqual(result.winner_id, "c02")
            self.assertEqual(report["candidates"]["c01"]["failures"], ["protected_path:test_value.py"])
            self.assertEqual(report["candidates"]["c01"]["checks"], [])
            self.assertEqual(report["candidates"]["c02"]["changed_files"], ["new.txt", "old.txt", "value.py"])
            self.assertEqual((repo / "test_value.py").read_text(), test_source)
            self.assertEqual((repo / "value.py").read_text(), "VALUE = 1\n")

    def test_parallel_candidates_are_graded_in_fresh_workspaces(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            init_repo(repo, {
                "clamp.py": "def clamp(value, lower, upper):\n    return value\n",
                "agent.py": (
                    "import os\n"
                    "from pathlib import Path\n"
                    "candidate = os.environ['PATCH_TOURNAMENT_CANDIDATE_ID']\n"
                    "if candidate == 'c01':\n"
                    "    Path('clamp.py').write_text('def clamp(value, lower, upper):\\n    return max(lower, min(value, upper))\\n')\n"
                    "elif candidate == 'c02':\n"
                    "    Path('clamp.py').write_text('def clamp(value, lower, upper):\\n    bounded = min(value, upper)\\n    return max(lower, bounded)\\n')\n"
                    "    Path('architecture.py').write_text('class ClampArchitecture:\\n    pass\\n')\n"
                    "else:\n"
                    "    Path('clamp.py').write_text('def clamp(value, lower, upper):\\n    return lower\\n')\n"
                ),
            })
            issue = root / "issue.md"
            issue.write_text("Clamp values below and above both bounds.\n", encoding="utf-8")
            hidden = root / "test_hidden.py"
            hidden.write_text(
                "import unittest\nfrom clamp import clamp\n\n"
                "class ClampTests(unittest.TestCase):\n"
                "    def test_both_bounds(self):\n"
                "        self.assertEqual(clamp(-1, 0, 10), 0)\n"
                "        self.assertEqual(clamp(11, 0, 10), 10)\n"
                "        self.assertEqual(clamp(5, 0, 10), 5)\n",
                encoding="utf-8",
            )
            config = root / "tournament.toml"
            config.write_text(
                "version = 1\n"
                "[project]\nrepo = \"repo\"\nref = \"HEAD\"\n"
                "[[sources]]\nkind = \"issue\"\npath = \"issue.md\"\nvisible = true\n"
                "[candidates]\nadapter = \"command\"\ncommand = [\"python3\", \"agent.py\"]\n"
                "count = 3\nconcurrency = 3\ntimeout_seconds = 20\n"
                "[[checks]]\nid = \"hidden-regression\"\nkind = \"approved-hidden\"\n"
                "evidence_paths = [\"test_hidden.py\"]\n"
                "command = [\"python3\", \"-m\", \"unittest\", \"test_hidden.py\"]\n"
                "baseline = \"fail\"\ntimeout_seconds = 20\n"
                "[[checks]]\nid = \"advisory\"\nkind = \"speculative\"\n"
                "command = [\"python3\", \"-c\", \"raise SystemExit(1)\"]\n"
                "baseline = \"any\"\ntimeout_seconds = 20\n"
                "[[overlays]]\nkind = \"approved-hidden\"\nsource = \"test_hidden.py\"\n"
                "destination = \"test_hidden.py\"\n"
                "[selection]\ntest_globs = [\"test_*.py\"]\n"
                "[safety]\nreport_only = true\nprotected_paths = [\"pyproject.toml\"]\n",
                encoding="utf-8",
            )
            output = root / "output"

            result = run_tournament(config, output)

            self.assertEqual(result.status, "winner")
            self.assertEqual(result.winner_id, "c01")
            self.assertTrue((output / "winner.patch").exists())
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["winner_id"], "c01")
            self.assertEqual(report["candidates"]["c01"]["checks"][1]["result"]["status"], "failed")
            self.assertEqual(report["candidates"]["c03"]["status"], "ineligible")
            self.assertFalse((repo / "architecture.py").exists())
            self.assertIn("return value", (repo / "clamp.py").read_text(encoding="utf-8"))

    def test_candidate_python_bytecode_does_not_enter_winner_patch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            init_repo(repo, {
                "value.py": "VALUE = 1\n",
                "agent.py": (
                    "import value\n"
                    "from pathlib import Path\n"
                    "Path('value.py').write_text('VALUE = 2\\n', encoding='utf-8')\n"
                ),
                "test_hidden.py": (
                    "import unittest\n"
                    "from value import VALUE\n\n"
                    "class ValueTests(unittest.TestCase):\n"
                    "    def test_value(self):\n"
                    "        self.assertEqual(VALUE, 2)\n"
                ),
            })
            issue = root / "issue.md"
            issue.write_text("Make VALUE equal two.\n", encoding="utf-8")
            config = root / "tournament.toml"
            config.write_text(
                "version = 1\n"
                "[project]\nrepo = \"repo\"\nref = \"HEAD\"\n"
                "[[sources]]\nkind = \"issue\"\npath = \"issue.md\"\nvisible = true\n"
                "[candidates]\nadapter = \"command\"\ncommand = [\"python3\", \"agent.py\"]\n"
                "count = 1\nconcurrency = 1\ntimeout_seconds = 20\n"
                "[[checks]]\nid = \"hidden-regression\"\nkind = \"approved-hidden\"\n"
                "evidence_paths = [\"test_hidden.py\"]\n"
                "command = [\"python3\", \"-m\", \"unittest\", \"test_hidden.py\"]\n"
                "baseline = \"fail\"\ntimeout_seconds = 20\n"
                "[selection]\ntest_globs = [\"test_*.py\"]\n"
                "[safety]\nreport_only = true\n",
                encoding="utf-8",
            )
            output = root / "output"

            result = run_tournament(config, output)

            self.assertEqual(result.status, "winner")
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            winner_patch = (output / "winner.patch").read_text(encoding="utf-8")
            self.assertEqual(report["candidates"]["c01"]["changed_files"], ["value.py"])
            self.assertNotIn("__pycache__", winner_patch)
            self.assertNotIn(".pyc", winner_patch)
            self.assertFalse(any(repo.rglob("__pycache__")))


if __name__ == "__main__":
    unittest.main()
