# Home Maintenance MCP Server

A small, offline-first MCP (Model Context Protocol) server that keeps track of
your home's maintenance history and rhythm — in plain JSON, on your own
machine, with zero dependencies beyond Python's standard library.

Built to explain AI "like a friend would": run it, point your MCP client at
it, and ask *"what's due around the house this week?"*

From [Asdale Dynamics, LLC](https://dylanasdale.github.io) — companion to
*Dylan Asdale's* AI guides and MCP servers like `home-repair-with-ai-guide`
and `dates-to-remember-mcp-server` (this one focuses on recurring home
rhythm and history; those cover repair walkthroughs and personal dates).

## What it tracks

- **Systems** — furnace, water heater, roof, appliances: location, install
  date, notes.
- **Recurring tasks** — filter changes, smoke-detector tests, gutter sweeps:
  an interval in days, plus an optional *seasonal window* (e.g. gutters only
  fall in April and October).
- **History & costs** — contractor visits, service calls, DIY fixes and
  inspections, with cost totals.
- **Paperwork** — where the manual lives (hall closet bin #1?) and when the
  warranty expires, with notes.
- **What's due** — one query returns everything overdue, due soon, and any
  warranties expiring, sorted worst-first.

## Quickstart

Requires Python 3.10+ (tested on 3.13). No packages to install.

```bash
git clone <this repo> home-maintenance-mcp-server
cd home-maintenance-mcp-server

# Smoke-test it end to end first (recommended):
python3 smoke_test.py

# Run the server (stdio MCP), seeded with a sample home:
python3 -m home_maintenance.server --sample
```

The first time you make a change, the server writes `home_data.json` next to
where you ran it. Point it at a different file by passing a path:

```bash
python3 -m home_maintenance.server my_home_data.json
```

### MCP client configuration

Add this to your MCP client (opencode, Claude Desktop-style config, etc. —
adjust the paths to your machine):

```json
{
  "mcpServers": {
    "home-maintenance": {
      "command": "python3",
      "args": ["-m", "home_maintenance.server", "home_data.json", "--sample"],
      "cwd": "/path/to/home-maintenance-mcp-server"
    }
  }
}
```

Then talk to your assistant naturally: "Log that the chimney guy came
Tuesday for $95", "What's due on the house?", "Where's the furnace manual?".

## Tools exposed

| Tool | Purpose |
| --- | --- |
| `get_due` | What's overdue / due soon / warranties expiring (worst-first). |
| `add_system` / `list_systems` | Register and list home systems. |
| `add_task` / `list_tasks` / `complete_task` | Recurring tasks and "did it today" resets. |
| `record_event` / `list_events` | Log and browse history: contractor visits, service, DIY, costs. |
| `add_document` / `list_documents` | Manual locations and warranty expiry with notes. |

`record_event` with a `task_id` also restarts that task's clock — logging
"filter swap" marks the filter task done.

## Smoke-test guide

`smoke_test.py` launches the real server as a subprocess and verifies, in
order:

1. `initialize` handshake returns the `home-maintenance` server info.
2. `tools/list` exposes the full tool set.
3. `--sample` seeds a home with an overdue gutter sweep and a due-soon smoke
   detector test (as of 2026-10-26 in the sample data).
4. A system plus a $95 contractor visit are recorded.
5. `home_data.json` is created and an auto-backup lands in `backups/`.
6. A `../escape.json` traversal path is refused with exit code 2.
7. A malformed line returns a JSON-RPC parse error and the session survives.

Run it any time:

```bash
python3 smoke_test.py          # end-to-end over stdio
python3 -m unittest discover -s tests   # 90 offline unit tests
```

### Try it by hand

Pipe raw JSON-RPC into the server:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_due","arguments":{"as_of":"2026-10-26"}}}' \
  | python3 -m home_maintenance.server nurture.json --sample
```

## How your data is stored

- One JSON file (default `home_data.json`) — readable, greppable, yours.
- **Path safety:** the data file must resolve inside the folder you started
  the server from, must be a `.json` file, and `..` escapes and symlink
  escapes are refused. Every path is resolved with `Path.resolve()` before
  any file touches, so `/etc/passwd` tricks fail shut.
- **Auto-backup:** before every write, the previous file is copied to
  `backups/home_data-<timestamp>.json` and backups are pruned to the 10 most
  recent. If the main file is ever corrupted, the server reloads itself from
  the newest valid backup automatically.
- Writes are atomic (temp file + `os.replace`) and fsynced.
- No network access, no telemetry, no secrets — ever.

## Sample home

`--sample` (also used when no data file exists yet) seeds:

- 3 systems: gas furnace, water heater, fridge
- 3 tasks: furnace filter (90 days), smoke-detector test (30 days), gutter
  sweep (90 days but only April/October since it's seasonal)
- 2 events: a $189 contractor furnace tune-up and a DIY spring gutter sweep
- 2 documents: furnace manual/warranty in "hall closet bin #1", water heater
  warranty in the junk-drawer binder

Ask for `get_due` with September-ish dates vs late October to watch the
seasonal gutter math slip Oct 1 forward. Delete `home_data.json` to start
over fresh (or keep it as scratch).

## Project layout

```
home_maintenance/
  recurrence.py   date math: intervals, seasonal slips, due classification
  storage.py      JSON storage: path safety, atomic writes, auto-backup
  tools.py        the ten tool handlers
  protocol.py     MCP framing: JSON-RPC 2.0 over newline-delimited stdio
  sample.py       the sample home data
tests/            90 offline unit tests (recurrence, security, tools, protocol)
smoke_test.py     end-to-end subprocess smoke test
```

## Known gaps

- Recurrence is day-count based (with seasonal month windows), not
  calendar-rule based (no "3rd Tuesday of October" natively).
- Single-user: no locking if you point multiple servers at one data file.
- No notes-as-markdown rendering; values are plain strings.
- A smart smoke-detector reminder will never replace an actual 9-volt.

## License

MIT — Copyright (c) 2026 **Asdale Dynamics, LLC**. See `LICENSE`.
