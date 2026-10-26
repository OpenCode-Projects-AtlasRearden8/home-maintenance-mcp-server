"""Offline tests for the MCP/JSON-RPC protocol layer."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from home_maintenance.protocol import (
    PARSE_ERROR,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    PROTOCOL_VERSION,
    Dispatcher,
    dispatch_line,
)
from home_maintenance.storage import Storage
from home_maintenance.tools import Toolbox


class ProtocolTestCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="hm-proto-"))
        self.storage = Storage(self.base, "home_data.json")
        self.dispatcher = Dispatcher(Toolbox(self.storage))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _init(self):
        return self.dispatcher.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )

    def test_initialize_reports_server_info(self):
        response = self._init()
        self.assertEqual(response["result"]["serverInfo"]["name"], "home-maintenance")
        self.assertIn("tools", response["result"]["capabilities"])

    def test_initialize_echoes_requested_version(self):
        response = self.dispatcher.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}}
        )
        self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")

    def test_ping(self):
        response = self.dispatcher.handle_message({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        self.assertEqual(response["result"], {})

    def test_tools_list_exposes_the_expected_set(self):
        response = self.dispatcher.handle_message(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
        )
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(
            names,
            [
                "get_due",
                "add_system",
                "list_systems",
                "add_task",
                "list_tasks",
                "complete_task",
                "record_event",
                "list_events",
                "add_document",
                "list_documents",
            ],
        )

    def test_tool_call_add_system(self):
        response = self.dispatcher.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "add_system",
                    "arguments": {"name": "Roof", "category": "Exterior"},
                },
            }
        )
        self.assertFalse(response["result"]["isError"])
        text = response["result"]["content"][0]["text"]
        self.assertIn("Roof", text)

    def test_tool_call_invalid_arguments_is_a_clean_error(self):
        response = self.dispatcher.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "add_system", "arguments": {}},
            }
        )
        self.assertEqual(response["error"]["code"], INVALID_PARAMS)

    def test_unknown_tool(self):
        response = self.dispatcher.handle_message(
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "rm_rf"}}
        )
        self.assertEqual(response["error"]["code"], METHOD_NOT_FOUND)

    def test_unknown_method(self):
        response = self.dispatcher.handle_message(
            {"jsonrpc": "2.0", "id": 7, "method": "resources/list"}
        )
        self.assertEqual(response["error"]["code"], METHOD_NOT_FOUND)

    def test_notification_gets_no_response(self):
        response = self.dispatcher.handle_message(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        self.assertIsNone(response)

    def test_malformed_jsonrpc_version(self):
        response = self.dispatcher.handle_message({"jsonrpc": "1.0", "id": 8, "method": "ping"})
        self.assertEqual(response["error"]["code"], PARSE_ERROR)

    def test_non_object_message(self):
        response = self.dispatcher.handle_message(["not", "an", "object"])
        self.assertEqual(response["error"]["code"], PARSE_ERROR)
        self.assertIsNone(response["id"])

    def test_bad_params_type(self):
        response = self.dispatcher.handle_message(
            {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": [1, 2]}
        )
        self.assertEqual(response["error"]["code"], INVALID_PARAMS)

    def test_missing_method(self):
        response = self.dispatcher.handle_message({"jsonrpc": "2.0", "id": 10})
        self.assertEqual(response["error"]["code"], PARSE_ERROR)


class LineFramingTests(ProtocolTestCase):
    def test_dispatch_line_roundtrip(self):
        line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        out = dispatch_line(self.dispatcher, line)
        payload = json.loads(out)
        self.assertEqual(payload["id"], 1)
        self.assertTrue(out.endswith('"result": {}') or json.loads(out)["result"] == {})

    def test_blank_line_is_skipped(self):
        self.assertIsNone(dispatch_line(self.dispatcher, "\n"))
        self.assertIsNone(dispatch_line(self.dispatcher, "   "))

    def test_corrupt_line_returns_parse_error(self):
        out = dispatch_line(self.dispatcher, "{oops")
        payload = json.loads(out)
        self.assertEqual(payload["error"]["code"], PARSE_ERROR)
        self.assertIsNone(payload["id"])

    def test_notification_line_writes_nothing(self):
        line = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(dispatch_line(self.dispatcher, line))


if __name__ == "__main__":
    unittest.main()
