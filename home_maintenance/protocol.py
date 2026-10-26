"""JSON-RPC 2.0 / MCP protocol handling for the stdio server."""

from __future__ import annotations

import json
import sys

from . import __version__

PROTOCOL_VERSION = "2024-11-05"
METHOD_NOT_FOUND = -32601
PARSE_ERROR = -32700
INVALID_PARAMS = -32602
TOOL_NOT_FOUND = -32601

TOOL_DEFINITIONS = [
    {
        "name": "get_due",
        "description": (
            "List what maintenance rhythm work is due or overdue within a lookahead "
            "window, sorted worst-first: filter changes, smoke-test dates, gutter "
            "sweeps, plus warranties that are expiring or expired."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "horizon_days": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 365,
                    "default": 14,
                    "description": "How many days ahead to look.",
                },
                "as_of": {
                    "type": "string",
                    "description": "YYYY-MM-DD; defaults to today.",
                },
            },
        },
    },
    {
        "name": "add_system",
        "description": "Add a home system (furnace, water heater, roof, appliance...).",
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "category": {
                    "type": "string",
                    "description": "HVAC, Plumbing, Electrical, Appliance, Exterior...",
                },
                "location": {"type": "string"},
                "installed": {"type": "string", "description": "YYYY-MM-DD"},
                "notes": {"type": "string"},
            },
        },
    },
    {
        "name": "list_systems",
        "description": "List every system on file.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_task",
        "description": (
            "Add a recurring maintenance task (e.g. replace furnace filter every 90 "
            "days, test smoke detectors every 30 days, gutter sweep seasonally)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["name", "interval_days"],
            "properties": {
                "name": {"type": "string"},
                "interval_days": {"type": "integer", "minimum": 1},
                "last_done": {"type": "string", "description": "YYYY-MM-DD"},
                "season_months": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": 12},
                    "description": "If set, the task can only fall in these months (1=Jan...12=Dec).",
                },
                "system_id": {"type": "string"},
                "notes": {"type": "string"},
            },
        },
    },
    {
        "name": "list_tasks",
        "description": "List every recurring task on file.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "complete_task",
        "description": "Mark a recurring task as done on a date, restarting its clock.",
        "inputSchema": {
            "type": "object",
            "required": ["task_id"],
            "properties": {
                "task_id": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD; defaults to today."},
            },
        },
    },
    {
        "name": "record_event",
        "description": (
            "Log a maintenance history event: a contractor visit, a service call, a "
            "DIY fix, or an inspection. Capture who came, what it cost, and notes."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["summary"],
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD; defaults to today."},
                "summary": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["contractor", "service", "diy", "repair", "inspection"],
                },
                "system_id": {"type": "string"},
                "task_id": {
                    "type": "string",
                    "description": "If given, also marks that recurring task done on this date.",
                },
                "contractor": {"type": "string"},
                "cost": {"type": "number", "minimum": 0},
                "notes": {"type": "string"},
            },
        },
    },
    {
        "name": "list_events",
        "description": "List maintenance history events, newest first, with cost total.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "system_id": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["contractor", "service", "diy", "repair", "inspection"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        },
    },
    {
        "name": "add_document",
        "description": (
            "Track where a manual lives and when a warranty expires, with notes "
            "(e.g. 'furnace manual, hall closet bin #1, warranty to 2029')."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["title"],
            "properties": {
                "title": {"type": "string"},
                "system_id": {"type": "string"},
                "warranty_until": {"type": "string", "description": "YYYY-MM-DD"},
                "manual_location": {"type": "string"},
                "notes": {"type": "string"},
            },
        },
    },
    {
        "name": "list_documents",
        "description": "List all warranty and manual-location records.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


KNOWN_TOOLS = {t["name"] for t in TOOL_DEFINITIONS}


class Dispatcher:
    """Dispatches decoded MCP messages against a Toolbox."""

    def __init__(self, toolbox):
        self.toolbox = toolbox

    def handle_message(self, message):
        """Return a response dict, or None for notifications/bad frames of no id."""
        if not isinstance(message, dict):
            return self._error(None, PARSE_ERROR, "message must be a JSON object")
        if message.get("jsonrpc") != "2.0":
            return self._error(message.get("id"), PARSE_ERROR, "jsonrpc must be exactly '2.0'")
        method = message.get("method")
        message_id = message.get("id")
        if not isinstance(method, str):
            return self._error(message_id, PARSE_ERROR, "method must be a string")
        params = message.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            if message_id is None:
                return None
            return self._error(message_id, INVALID_PARAMS, "params must be an object")
        if "id" not in message:
            return None
        try:
            result = self._dispatch(method, params)
        except TOOL_ERRORS as exc:
            return self._error(message_id, INVALID_PARAMS, str(exc))
        except UnknownMethodError as exc:
            return self._error(message_id, METHOD_NOT_FOUND, str(exc))
        except Exception as exc:  # defensive: never let the server die mid-stream
            return self._error(message_id, INVALID_PARAMS, f"internal error: {exc}")
        return {"jsonrpc": "2.0", "id": message_id, "result": result}

    def _dispatch(self, method: str, params: dict):
        if method == "initialize":
            requested = params.get("protocolVersion")
            return {
                "protocolVersion": requested if isinstance(requested, str) else PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": self.toolbox.name, "version": __version__},
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": TOOL_DEFINITIONS}
        if method == "tools/call":
            return self._call_tool(params)
        raise UnknownMethodError(method)

    def _call_tool(self, params: dict):
        name = params.get("name")
        if not isinstance(name, str):
            raise ToolInputError("tools/call requires a tool name")
        handler = getattr(self.toolbox, name, None)
        if name not in KNOWN_TOOLS or handler is None:
            raise UnknownMethodError(f"tool not found: {name}")
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ToolInputError("tool arguments must be an object")
        raw = handler(arguments)
        return {
            "content": [
                {"type": "text", "text": json.dumps(raw, indent=2, sort_keys=True, ensure_ascii=True)}
            ],
            "isError": False,
        }

    @staticmethod
    def _error(message_id, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {"code": code, "message": message},
        }


class ToolInputError(ValueError):
    pass


class UnknownMethodError(Exception):
    pass


TOOL_ERRORS = (ToolInputError, ValueError, KeyError)


def dispatch_line(dispatcher: Dispatcher, line: str):
    """Decode one newline-delimited message; returns a JSON line or None."""
    if not line.strip():
        return None
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        return json.dumps(dispatcher._error(None, PARSE_ERROR, "invalid JSON"), ensure_ascii=True)
    response = dispatcher.handle_message(message)
    if response is None:
        return None
    return json.dumps(response, ensure_ascii=True)


def serve(dispatcher: Dispatcher, reader, writer) -> None:
    """Read newline-delimited MCP messages until EOF. Kept simple and offline."""
    for line in reader:
        out = dispatch_line(dispatcher, line)
        if out is None:
            continue
        writer.write(out + "\n")
        writer.flush()


def main() -> None:
    import argparse
    from pathlib import Path

    from .sample import SAMPLE_HOME
    from .storage import Storage
    from .tools import Toolbox

    parser = argparse.ArgumentParser(
        prog="home-maintenance-mcp",
        description="Home maintenance MCP server over stdio (tracking history and rhythm).",
    )
    parser.add_argument(
        "data_file",
        nargs="?",
        default="home_data.json",
        help="JSON data file path (must stay inside the folder you run from)",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="seed the data file with the sample home if it does not exist yet",
    )
    args = parser.parse_args()

    base_dir = Path.cwd()
    try:
        storage = Storage(base_dir, args.data_file)
        toolbox = Toolbox(storage, initial=dict(SAMPLE_HOME) if args.sample else None)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
    dispatcher = Dispatcher(toolbox)
    serve(dispatcher, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
