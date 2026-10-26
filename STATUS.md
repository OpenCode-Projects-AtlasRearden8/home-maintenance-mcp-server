# STATUS.md — home-maintenance-mcp-server

Authored by Asdale Dynamics, LLC. Generated as the final build report for this
repository, October 2026.

## What was built

A small, dependency-free MCP (Model Context Protocol) server — Python stdlib
only, JSON-RPC 2.0 over newline-delimited stdio — that tracks a home's
maintenance history and rhythm:

- **Systems** — `add_system` / `list_systems` (name, category, location,
  install date, notes).
- **Recurring tasks** — `add_task` / `list_tasks` / `complete_task`. An
  interval in days plus an optional `season_months` window (gutter sweeps that
  can only fall in April or October slide their due date to the first of the
  next in-season month).
- **History & costs** — `record_event` / `list_events` for contractor visits,
  service calls, DIY fixes, inspections; captures contractor, cost (validated
  non-negative, rounded to cents), notes; events with a `task_id` also
  restart that task's clock (forward-only).
- **Warranty & manual paperwork** — `add_document` / `list_documents` with
  manual location, warranty expiry, notes.
- **The "what's due" question** — `get_due` returns overdue / due-soon /
  never-done tasks plus expiring and expired warranties, sorted worst-first,
  with a configurable lookahead (default 14 days) and injectable "as of" date.

Storage (`home_maintenance/storage.py`): single JSON file with **path safety**
(paths must resolve inside the startup folder, `.json` suffix required, `..`
and symlink escapes rejected, directories refused) and **auto-backup** (every
write first copies the old file to `backups/`, timestamped, pruned to the 10
most recent, writes are atomic temp-file + `os.replace` + fsync). If the main
file is corrupted, the loader automatically falls back to the newest valid
backup.

Includes a **sample home** (`--sample`, also the default seed when no data
file exists): 3 systems, furnace filter / smoke-test / seasonal gutter tasks,
a $189 contractor tune-up, and manual/warranty documents.

## How to run it

```bash
python3 -m home_maintenance.server            # stdio MCP server, default data file
python3 -m home_maintenance.server --sample   # seed with the sample home
python3 smoke_test.py                         # end-to-end subprocess smoke test
python3 -m unittest discover -s tests         # offline unit tests
```

MCP client config example and a hand-piped JSON-RPC walkthrough are in
`README.md`.

## Verification results (as of this commit)

- `python3 -m unittest discover -s tests` → **90 tests, OK**
  - recurrence math: seasonal slips, leap years (Feb 29), year rollover,
    classification windows, cost/date/interval validation failures
  - security: `../` traversal, absolute-outside paths, symlink escapes,
    non-`.json` extensions, directory-as-file, empty/non-string paths
  - storage: roundtrip, revision bumps, backup creation + pruning, corrupt
    file recovery from backup, corrupt-without-backup failure, atomic writes
  - protocol: initialize/ping/tools-list, tool calls, unknown method (-32601),
    malformed JSON (-32700), notifications (no reply), garbage frames
  - real subprocess integration: full MCP session incl. sample seeding
- `python3 smoke_test.py` → **all 15 checks PASS** (handshake, tool list,
  sample due-state, contractor + $95 cost logging, data file + auto-backup,
  traversal refused with exit 2, malformed-frame survival)
- Server process exits nonzero (2) with a clear `error:` message for unsafe
  data paths.

## Known gaps

- Recurrence is day-count + seasonal-month-window based; no calendar rules
  (e.g. "3rd Tuesday of October") and no per-timezone handling.
- Single JSON file, so no multi-host locking if two servers share one file.
- `get_due` is the only read-side aggregation; no year-to-date cost report or
  per-system timeline yet (could be a natural next step).
- Tool schemas are hand-written; no automated schema-conformance test against
  the MCP spec version.
- Corrupt-without-backup fails loudly (by design) while no valid backups
  exist; users of very long sessions may want off-cloud snapshots.
- No packaging metadata (no `pyproject.toml`) — it runs as a repo, which fits
  the local-first, copy-and-go audience; add later if publishing to PyPI.

## Repo notes

- License: MIT, `Copyright (c) 2026 Asdale Dynamics, LLC`
- No secrets, keys, or personal data anywhere in the tree; sample data is
  fictional.
- No co-authored-by trailers on commits; repo remains local-only.
