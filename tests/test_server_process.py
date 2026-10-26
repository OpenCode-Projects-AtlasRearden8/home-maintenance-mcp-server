"""End-to-end test: spawn the real server as a subprocess over stdio."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class ServerProcessTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="hm-proc-"))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _run_session(self, messages, sample=True):
        with tempfile.NamedTemporaryFile(
            "w+", suffix=".json", delete=False, dir=self.base
        ) as handle:
            data_path = Path(handle.name)
        data_path.unlink()
        command = [sys.executable, "-m", "home_maintenance.server", str(data_path)]
        if sample:
            command.append("--sample")
        lines = [json.dumps(m) for m in messages]
        env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
        proc = subprocess.run(
            command,
            input="\n".join(lines) + "\n",
            cwd=self.base,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if proc.returncode != 0:
            self.fail(f"server exited {proc.returncode}: {proc.stderr}")
        return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]

    def test_full_session_initialize_call_and_due(self):
        session = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_due", "arguments": {"as_of": "2026-10-26"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "record_event",
                    "arguments": {
                        "summary": "Furnace filter swap",
                        "kind": "diy",
                        "cost": 12.99,
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "list_events", "arguments": {}},
            },
        ]
        responses = self._run_session(session)
        self.assertEqual(len(responses), 5)
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "home-maintenance")
        names = [t["name"] for t in responses[1]["result"]["tools"]]
        self.assertIn("get_due", names)
        task_payload = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertEqual(task_payload["as_of"], "2026-10-26")
        list_payload = json.loads(responses[4]["result"]["content"][0]["text"])
        self.assertTrue(any("filter swap" in e["summary"].lower() for e in list_payload["events"]))

    def test_hostile_path_argument_is_refused(self):
        command = [sys.executable, "-m", "home_maintenance.server", "/tmp/opencode-outside.json"]
        proc = subprocess.run(
            command,
            input="",
            cwd=self.base,
            capture_output=True,
            text=True,
            timeout=60,
            env=dict(os.environ, PYTHONPATH=str(REPO_ROOT)),
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", (proc.stderr + proc.stdout).lower())

    def test_empty_session_exits_cleanly(self):
        responses = self._run_session([])
        self.assertEqual(responses, [])


if __name__ == "__main__":
    unittest.main()
