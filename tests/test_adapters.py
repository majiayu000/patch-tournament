from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from patch_tournament.adapters import (
    build_candidate_invocation,
    build_task_prompt,
    prepare_codex_home,
)
from patch_tournament.config import CandidateConfig, SourceConfig


class AdapterTests(unittest.TestCase):
    def test_prompt_contains_only_visible_evidence_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            visible = root / "issue.md"
            hidden = root / "hidden.md"
            visible.write_text("Fix the boundary bug.\n", encoding="utf-8")
            hidden.write_text("SECRET ORACLE\n", encoding="utf-8")

            prompt = build_task_prompt((
                SourceConfig("issue", visible, True),
                SourceConfig("approved-hidden", hidden, False),
            ))

            self.assertIn("SOURCE kind=issue path=issue.md", prompt)
            self.assertIn("Fix the boundary bug.", prompt)
            self.assertNotIn("SECRET ORACLE", prompt)

    def test_codex_invocation_is_ephemeral_and_ignores_user_config(self) -> None:
        config = CandidateConfig(
            adapter="codex",
            command=(),
            count=1,
            concurrency=1,
            timeout_seconds=60,
            model="gpt-5.4",
            reasoning_effort="high",
        )
        invocation = build_candidate_invocation(config, Path("/tmp/work"), "Do the task.")

        self.assertEqual(invocation.args[:5], (
            "codex", "exec", "--ephemeral", "--json", "--ignore-user-config",
        ))
        self.assertIn(("--sandbox", "workspace-write"), tuple(zip(invocation.args, invocation.args[1:])))
        self.assertIn(("--cd", "/tmp/work"), tuple(zip(invocation.args, invocation.args[1:])))
        self.assertEqual(invocation.args[-1], "Do the task.")

    def test_command_invocation_preserves_argument_array(self) -> None:
        config = CandidateConfig("command", ("python3", "agent.py"), 1, 1, 60)
        invocation = build_candidate_invocation(config, Path("/tmp/work"), "Task")

        self.assertEqual(invocation.args, ("python3", "agent.py"))

    def test_isolated_codex_home_copies_only_auth_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            destination = root / "isolated"
            source.mkdir()
            (source / "auth.json").write_text('{"token":"test-only"}', encoding="utf-8")
            (source / "config.toml").write_text("danger = true", encoding="utf-8")

            prepare_codex_home(source, destination)

            self.assertTrue((destination / "auth.json").exists())
            self.assertFalse((destination / "config.toml").exists())
            self.assertEqual(os.stat(destination / "auth.json").st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
