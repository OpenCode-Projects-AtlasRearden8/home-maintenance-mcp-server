"""Offline tests for tool behavior and due-date queries."""

import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from home_maintenance.storage import Storage
from home_maintenance.tools import Toolbox
from home_maintenance.sample import SAMPLE_HOME


class ToolboxTestCase(unittest.TestCase):
    keep_temp = True

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="hm-tools-"))
        self.storage = Storage(self.base, "home_data.json")
        self.box = Toolbox(self.storage)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)


class GetDueTests(ToolboxTestCase):
    def setUp(self):
        super().setUp()
        self.box.doc = {**SAMPLE_HOME, "revision": 0}

    def sample_toolbox(self):
        self.box.doc = {**SAMPLE_HOME, "revision": 0}

    def test_sample_home_shapes_up_as_of_october(self):
        self.box.doc = {**SAMPLE_HOME, "revision": 0}
        result = self.box.get_due({"as_of": "2026-10-26"})
        items = result["items"]
        self.assertEqual(result["as_of"], "2026-10-26")
        self.assertEqual(items[0]["status"], "overdue")
        gutter = next(i for i in items if "gutter" in i["task"].lower())
        self.assertEqual(gutter["status"], "overdue")
        smoke = next(i for i in items if "smoke" in i["task"].lower())
        self.assertEqual(smoke["due_date"], "2026-10-28")
        self.assertEqual(smoke["status"], "due_soon")

    def test_seasonal_ok_right_after_sweep(self):
        self.box.doc = {**SAMPLE_HOME, "revision": 0}
        gutter_task = next(t for t in self.box.doc["tasks"] if "gutter" in t["name"].lower())
        gutter_task["last_done"] = "2026-10-03"
        result = self.box.get_due({"as_of": "2026-10-05"})
        gutter = next(i for i in result["items"] if "gutter" in i["task"].lower())
        self.assertEqual(gutter["due_date"], "2027-04-01")
        self.assertEqual(gutter["status"], "ok")

    def test_warranty_shows_expiring(self):
        self.box.doc = {**SAMPLE_HOME, "revision": 0}
        result = self.box.get_due({"as_of": "2027-02-20"})
        warrant = next(i for i in result["items"] if "Water heater" in i["task"])
        self.assertEqual(warrant["status"], "expiring_soon")

    def test_horizon_zero_still_flags_overdue(self):
        self.box.doc = {**SAMPLE_HOME, "revision": 0}
        result = self.box.get_due({"as_of": "2026-10-26", "horizon_days": 0})
        gutter = next(i for i in result["items"] if "gutter" in i["task"].lower())
        self.assertEqual(gutter["status"], "overdue")

    def test_invalid_horizon_rejected(self):
        with self.assertRaises(ValueError):
            self.box.get_due({"horizon_days": 400})
        with self.assertRaises(ValueError):
            self.box.get_due({"horizon_days": "two weeks"})

    def test_never_done_task_listed(self):
        self.box.add_task({"name": "Vacuum fridge coils", "interval_days": 180})
        result = self.box.get_due({"as_of": "2026-10-26"})
        vacuum = next(i for i in result["items"] if "coils" in i["task"])
        self.assertEqual(vacuum["status"], "never_done")
        self.assertIsNone(vacuum["due_date"])


class MutationTests(ToolboxTestCase):
    def test_add_and_list_system_roundtrip(self):
        self.box.add_system({"name": "Sump pump", "location": "Basement corner"})
        listing = self.box.list_systems({})
        self.assertEqual(listing["systems"][0]["name"], "Sump pump")

    def test_blank_name_rejected_and_nothing_saved(self):
        with self.assertRaises(ValueError):
            self.box.add_system({"name": "   "})
        self.assertEqual(len(self.box.doc["systems"]), 0)

    def test_task_interval_validation(self):
        with self.assertRaises(ValueError):
            self.box.add_task({"name": "Filter", "interval_days": 0})
        with self.assertRaises(ValueError):
            self.box.add_task({"name": "Filter", "interval_days": True})
        with self.assertRaises(ValueError):
            self.box.add_task({"name": "Filter", "interval_days": "90"})

    def test_task_with_unknown_system_rejected(self):
        with self.assertRaises(ValueError):
            self.box.add_task({"name": "X", "interval_days": 30, "system_id": "sys_ghost"})

    def test_unknown_system_reference_never_created(self):
        try:
            self.box.add_task({"name": "X", "interval_days": 30, "system_id": "sys_ghost"})
        except ValueError:
            pass
        self.assertEqual(len(self.box.doc["systems"]), 0)

    def test_record_event_cost_and_contractor(self):
        sys_result = self.box.add_system({"name": "Water heater"})
        event = self.box.record_event(
            {
                "date": "2026-10-10",
                "summary": "Annual flush and inspection",
                "kind": "contractor",
                "system_id": sys_result["system"]["id"],
                "contractor": "Brewster Plumbing",
                "cost": 149.5,
            }
        )
        self.assertEqual(event["event"]["cost"], 149.5)
        listed = self.box.list_events({"kind": "contractor"})
        self.assertEqual(listed["events"][0]["contractor"], "Brewster Plumbing")
        self.assertEqual(listed["total_cost"], 149.5)

    def test_negative_cost_rejected(self):
        with self.assertRaises(ValueError):
            self.box.record_event({"summary": "x", "cost": -20})
        with self.assertRaises(ValueError):
            self.box.record_event({"summary": "x", "cost": "roughly $"})

    def test_bad_date_rejected(self):
        with self.assertRaises(ValueError):
            self.box.record_event({"summary": "x", "date": "10/10/26"})

    def test_bad_kind_rejected(self):
        with self.assertRaises(ValueError):
            self.box.record_event({"summary": "x", "kind": "party"})

    def test_event_updates_task_last_done_forward_only(self):
        task = self.box.add_task({"name": "Filter", "interval_days": 90, "last_done": "2026-10-01"})
        self.box.record_event(
            {"summary": "filter swap", "kind": "diy", "task_id": task["task"]["id"], "date": "2026-10-15"}
        )
        self.assertEqual(self.box.list_tasks({})["tasks"][0]["last_done"], "2026-10-15")
        self.box.record_event(
            {"summary": "oops backdated", "kind": "diy", "task_id": task["task"]["id"], "date": "2026-01-01"}
        )
        self.assertEqual(self.box.list_tasks({})["tasks"][0]["last_done"], "2026-10-15")

    def test_complete_task_sets_last_done(self):
        task = self.box.add_task({"name": "Pump test", "interval_days": 30})
        self.box.complete_task({"task_id": task["task"]["id"], "date": "2026-10-26"})
        self.assertEqual(self.box.list_tasks({})["tasks"][0]["last_done"], "2026-10-26")
        with self.assertRaises(ValueError):
            self.box.complete_task({"task_id": "task_ghost"})

    def test_document_tracking(self):
        sys_result = self.box.add_system({"name": "Refrigerator"})
        self.box.add_document(
            {
                "title": "Fridge manual",
                "system_id": sys_result["system"]["id"],
                "warranty_until": "2028-07-20",
                "manual_location": "Kitchen drawer",
            }
        )
        docs = self.box.list_documents({})
        self.assertEqual(docs["count"], 1)
        self.assertEqual(docs["documents"][0]["manual_location"], "Kitchen drawer")
        with self.assertRaises(ValueError):
            self.box.add_document({"title": "", "warranty_until": "someday"})

    def test_every_write_persists_to_disk(self):
        self.box.add_system({"name": "Sump pump"})
        reloaded = Toolbox(self.storage)
        self.assertEqual(reloaded.list_systems({})["count"], 1)


if __name__ == "__main__":
    unittest.main()
