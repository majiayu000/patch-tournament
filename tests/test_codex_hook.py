from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from patch_tournament.codex_hook import handle_event, main
from tests.helpers import init_repo


def hook_event(name: str, repo: Path, *, stop_hook_active: bool = False) -> dict[str, object]:
    return {
        "session_id": "session-123",
        "turn_id": "turn-456",
        "cwd": str(repo),
        "hook_event_name": name,
        "stop_hook_active": stop_hook_active,
    }


class CodexHookTests(unittest.TestCase):
    def test_stop_reports_task_owned_changes_without_requesting_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            data = root / "plugin-data"
            init_repo(repo, {"app.py": "VALUE = 1\n"})
            (repo / "legacy.py").write_text("LEGACY = True\n", encoding="utf-8")

            self.assertEqual(handle_event(hook_event("PreToolUse", repo), data), {})
            self.assertEqual(len(list((data / "snapshots").glob("*.json"))), 1)

            (repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
            result = handle_event(hook_event("Stop", repo), data)

            self.assertEqual(set(result), {"systemMessage"})
            message = str(result["systemMessage"])
            self.assertIn("[info]", message)
            self.assertIn("status=observed", message)
            self.assertIn("M app.py (+1/-1)", message)
            self.assertNotIn("legacy.py", message)
            self.assertIn("DO NOT:", message)

    def test_pre_tool_snapshot_is_idempotent_for_parallel_tool_calls(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            data = root / "plugin-data"
            init_repo(repo, {"app.py": "VALUE = 1\n"})
            event = hook_event("PreToolUse", repo)

            self.assertEqual(handle_event(event, data), {})
            self.assertEqual(handle_event(event, data), {})

            self.assertEqual(len(list((data / "snapshots").glob("*.json"))), 1)

    def test_stop_is_quiet_for_empty_diff_and_second_stop_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            data = root / "plugin-data"
            init_repo(repo, {"app.py": "VALUE = 1\n"})
            handle_event(hook_event("PreToolUse", repo), data)

            self.assertEqual(handle_event(hook_event("Stop", repo), data), {})
            self.assertEqual(
                handle_event(hook_event("Stop", repo, stop_hook_active=True), data),
                {},
            )

    def test_non_git_working_directory_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            data = root / "plugin-data"

            self.assertEqual(handle_event(hook_event("PreToolUse", root), data), {})
            self.assertFalse((data / "snapshots").exists())

    def test_main_emits_machine_readable_error_context(self) -> None:
        stdout = io.StringIO()
        with patch.dict(os.environ, {"PLUGIN_DATA": "/tmp/patch-guard-test-data"}, clear=False):
            with patch("sys.stdin", io.StringIO("not-json")), redirect_stdout(stdout):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("systemMessage", payload)
        self.assertIn("task attribution unavailable", payload["systemMessage"])


class PluginPackageTests(unittest.TestCase):
    def test_repository_exposes_plugin_through_marketplace(self) -> None:
        root = Path(__file__).resolve().parents[1]
        marketplace = json.loads(
            (root / ".agents" / "plugins" / "marketplace.json").read_text()
        )

        self.assertEqual(marketplace["name"], "patch-tournament")
        self.assertEqual(marketplace["interface"]["displayName"], "Patch Tournament")
        self.assertEqual(
            marketplace["plugins"],
            [
                {
                    "name": "patch-guard",
                    "source": {"source": "local", "path": "."},
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": "Developer Tools",
                }
            ],
        )

    def test_manifest_and_default_hook_bundle_are_valid_minimal_shape(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / ".codex-plugin" / "plugin.json").read_text())
        hooks = json.loads((root / "hooks" / "hooks.json").read_text())

        self.assertEqual(manifest["name"], "patch-guard")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("hooks", manifest)
        self.assertEqual(set(hooks["hooks"]), {"PreToolUse", "Stop"})
        pre_tool = hooks["hooks"]["PreToolUse"][0]["hooks"][0]
        stop = hooks["hooks"]["Stop"][0]["hooks"][0]
        self.assertIn("$PLUGIN_ROOT/src", pre_tool["command"])
        self.assertEqual(pre_tool["command"], stop["command"])


if __name__ == "__main__":
    unittest.main()
