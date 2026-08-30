from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from patch_tournament.config import ConfigError, load_config


VALID_CONFIG = """
version = 1

[project]
repo = "repo"
ref = "HEAD"

[[sources]]
kind = "issue"
path = "issue.md"
visible = true

[candidates]
adapter = "command"
command = ["python3", "agent.py"]
count = 3
concurrency = 2
timeout_seconds = 60

[[checks]]
id = "regression"
kind = "reproduction"
command = ["python3", "-m", "unittest"]
baseline = "fail"
timeout_seconds = 30

[selection]
test_globs = ["tests/**", "**/*_test.py"]

[safety]
report_only = true
protected_paths = ["pyproject.toml"]
"""


class ConfigTests(unittest.TestCase):
    def write_config(self, root: Path, text: str = VALID_CONFIG) -> Path:
        path = root / "tournament.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_loads_and_resolves_evidence_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "repo").mkdir()
            (root / "issue.md").write_text("Fix the bug.\n", encoding="utf-8")

            config = load_config(self.write_config(root))

            self.assertEqual(config.project.repo, (root / "repo").resolve())
            self.assertEqual(config.candidates.count, 3)
            self.assertEqual(config.checks[0].baseline, "fail")
            self.assertTrue(config.checks[0].gating)
            self.assertEqual(config.sources[0].path, (root / "issue.md").resolve())
            self.assertTrue(config.safety.report_only)

    def test_speculative_check_can_never_gate_selection(self) -> None:
        text = VALID_CONFIG.replace('kind = "reproduction"', 'kind = "speculative"')
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "repo").mkdir()
            (root / "issue.md").write_text("Fix the bug.\n", encoding="utf-8")

            config = load_config(self.write_config(root, text))

            self.assertFalse(config.checks[0].gating)

    def test_rejects_shell_string_commands(self) -> None:
        text = VALID_CONFIG.replace(
            'command = ["python3", "-m", "unittest"]',
            'command = "python3 -m unittest"',
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "repo").mkdir()
            (root / "issue.md").write_text("Fix the bug.\n", encoding="utf-8")

            with self.assertRaisesRegex(ConfigError, "array of arguments"):
                load_config(self.write_config(root, text))

    def test_v1_requires_report_only_mode(self) -> None:
        text = VALID_CONFIG.replace("report_only = true", "report_only = false")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "repo").mkdir()
            (root / "issue.md").write_text("Fix the bug.\n", encoding="utf-8")

            with self.assertRaisesRegex(ConfigError, "report_only"):
                load_config(self.write_config(root, text))
