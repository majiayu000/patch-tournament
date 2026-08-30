from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from patch_tournament.cli import main
from patch_tournament.runner import TournamentRunResult


class CliTests(unittest.TestCase):
    def test_no_winner_uses_machine_readable_exit_code_two(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            result = TournamentRunResult("no_winner", None, 0, root / "report.json")
            with patch("patch_tournament.cli.run_tournament", return_value=result):
                exit_code = main(["run", "--config", "input.toml", "--output", "result"])

        self.assertEqual(exit_code, 2)

    def test_configuration_error_uses_exit_code_one(self) -> None:
        with patch("patch_tournament.cli.run_tournament", side_effect=ValueError("bad config")):
            exit_code = main(["run", "--config", "input.toml", "--output", "result"])

        self.assertEqual(exit_code, 1)

    def test_missing_codex_auth_is_reported_without_traceback(self) -> None:
        with patch(
            "patch_tournament.cli.run_tournament",
            side_effect=FileNotFoundError("Codex auth file does not exist"),
        ):
            exit_code = main(["run", "--config", "input.toml", "--output", "result"])

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
