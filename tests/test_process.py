from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from patch_tournament.process import run_command


class ProcessTests(unittest.TestCase):
    def test_nonzero_exit_preserves_stdout_and_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            result = run_command(
                ["python3", "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(7)"],
                Path(raw),
                timeout_seconds=10,
            )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.returncode, 7)
        self.assertIn("out", result.stdout)
        self.assertIn("err", result.stderr)

    def test_timeout_is_an_explicit_result(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            result = run_command(
                ["python3", "-c", "import time; time.sleep(2)"],
                Path(raw),
                timeout_seconds=1,
            )

        self.assertEqual(result.status, "timeout")
        self.assertIsNone(result.returncode)


if __name__ == "__main__":
    unittest.main()
