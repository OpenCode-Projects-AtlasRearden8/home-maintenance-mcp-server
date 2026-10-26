#!/usr/bin/env python3
"""Drive the MCP server end to end over stdio, like an MCP client would.

Run from the repo root:  python3 smoke_test.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    color = GREEN if condition else RED
    print(f"  [{color}{mark}{RESET}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        raise SystemExit(1)


def main():
    workdir = Path(tempfile.mkdtemp(prefix="home-maintenance-smoke-"))
    data_path = workdir / "smoke_data.json"

    def send(messages):
        lines = "\n".join(json.dumps(m) for m in messages) + "\n"
        env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
        proc = subprocess.run(
            [sys.executable, "-m", "home_maintenance.server", str(data_path), "--sample"],
            input=lines,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if proc.returncode != 0:
            raise SystemExit(f"smoke test: server exited {proc.returncode}\n{proc.stderr}")
        return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]

    print("1. initialize handshake")
    (init,) = send([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])
    info = init["result"]["serverInfo"]
    check("serverInfo.name is home-maintenance", info["name"] == "home-maintenance", str(info))

    print("2. tools/list")
    (listing,) = send([{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
    names = [t["name"] for t in listing["result"]["tools"]]
    check("expected tools exposed", {"get_due", "add_task", "record_event"} <= set(names), str(names))

    print("3. sample home seeds correctly")
    (due,) = send(
        [
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_due", "arguments": {"as_of": "2026-10-26"}},
            }
        ]
    )
    payload = json.loads(due["result"]["content"][0]["text"])
    statuses = {i["status"] for i in payload["items"]}
    check("sample has overdue items", "overdue" in statuses, str(statuses))
    check("sample has due-soon items", "due_soon" in statuses, str(statuses))

    print("4. add a system, log a contractor visit with cost")
    added, visit = send(
        [
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "add_system",
                    "arguments": {"name": "Smoke-test furnace insert", "category": "HVAC"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "record_event",
                    "arguments": {
                        "date": "2026-10-20",
                        "summary": "Chimney inspection",
                        "kind": "contractor",
                        "contractor": "Sooty Chimneys LLC",
                        "cost": 95.0,
                    },
                },
            },
        ]
    )
    event = json.loads(visit["result"]["content"][0]["text"])["event"]
    check("contractor visit recorded", event["contractor"] == "Sooty Chimneys LLC")
    check("cost recorded", event["cost"] == 95.0, str(event["cost"]))

    print("5. data file created and backup made on second write")
    check("data file exists", data_path.exists())
    backup_dir = workdir / "backups"
    check("auto-backup exists", backup_dir.is_dir() and len(list(backup_dir.glob("*.json"))) >= 1)

    print("6. path safety: traversal file is refused")
    proc = subprocess.run(
        [sys.executable, "-m", "home_maintenance.server", "../escape.json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined = proc.stderr + proc.stdout
    check("traversal refused", proc.returncode == 2 and "not allowed" in combined.lower(), combined)

    print("7. malformed frame gets a parse error, session survives")
    workdir2 = Path(tempfile.mkdtemp(prefix="home-maintenance-smoke2-"))
    cmd = [sys.executable, "-m", "home_maintenance.server", str(workdir2 / "d.json")]
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    proc = subprocess.run(
        cmd,
        input="not json\n" + json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n",
        cwd=workdir2,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    lines = [json.loads(x) for x in proc.stdout.splitlines() if x.strip()]
    check("parse error returned", lines and lines[0]["error"]["code"] == -32700)
    check("server still answers after bad frame", lines[-1]["result"] == {})

    shutil.rmtree(workdir, ignore_errors=True)
    shutil.rmtree(workdir2, ignore_errors=True)
    print(f"\n{GREEN}All smoke checks passed.{RESET}")


if __name__ == "__main__":
    main()
