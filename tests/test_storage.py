"""Offline security and integrity tests for JSON storage."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from home_maintenance.storage import (
    PathSafetyError,
    StoreCorruptError,
    Storage,
    empty_document,
    new_id,
    resolve_within,
)


class PathSafetyTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="hm-base-"))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_relative_path_stays_valid(self):
        path = resolve_within(self.base, "home_data.json")
        self.assertEqual(path.parent, self.base)

    def test_nested_path_allowed_and_created_later(self):
        path = resolve_within(self.base, "homes/october/data.json")
        self.assertTrue(str(path).startswith(str(self.base)))

    def test_parent_traversal_rejected(self):
        with self.assertRaises(PathSafetyError):
            resolve_within(self.base, "../outside.json")
        with self.assertRaises(PathSafetyError):
            resolve_within(self.base, "sub/../../outside.json")

    def test_absolute_outside_rejected(self):
        with self.assertRaises(PathSafetyError):
            resolve_within(self.base, "/tmp/opencode/evil.json")

    def test_dotdot_only_wins_over_prefix_tricks(self):
        with self.assertRaises(PathSafetyError):
            resolve_within(self.base, "good/../../../../etc/passwd.json")

    def test_non_json_extension_rejected(self):
        with self.assertRaises(PathSafetyError):
            resolve_within(self.base, "home_data.txt")

    def test_symlink_escape_rejected(self):
        link = self.base / "sneaky.json"
        link.symlink_to(tempfile.gettempdir() + "/definitely-outside.json")
        with self.assertRaises(PathSafetyError):
            resolve_within(self.base, "sneaky.json")

    def test_empty_and_nonstring_paths_rejected(self):
        with self.assertRaises(PathSafetyError):
            resolve_within(self.base, "")
        with self.assertRaises(PathSafetyError):
            resolve_within(self.base, None)
        with self.assertRaises(PathSafetyError):
            resolve_within(self.base, 3.7)


class StorageRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="hm-rt-"))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _storage(self, name="home_data.json", keep=3):
        return Storage(self.base, name, keep_backups=keep)

    def test_missing_file_returns_fresh_or_seeded_document(self):
        self.assertEqual(self._storage().load(), empty_document())
        seeded = self._storage().load(initial={"hello": [1]})
        self.assertEqual(seeded["hello"], [1])

    def test_roundtrip_preserves_data(self):
        storage = self._storage()
        doc = empty_document()
        doc["systems"] = [{"id": "sys_x", "name": "Furnace"}]
        storage.save(doc)
        again = self._storage().load()
        self.assertEqual(again["systems"][0]["name"], "Furnace")

    def test_revision_bumps_each_save(self):
        storage = self._storage()
        doc = empty_document()
        storage.save(doc)
        storage.save(doc)
        self.assertEqual(self._storage().load()["revision"], 2)

    def test_auto_backup_created_timestamped(self):
        storage = self._storage()
        doc = empty_document()
        storage.save(doc)
        storage.save(doc)
        backups = storage.backup_names()
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].startswith("home_data-"))

    def test_backup_pruning_keeps_limit(self):
        storage = self._storage(keep=3)
        doc = empty_document()
        for _ in range(6):
            storage.save(doc)
        self.assertEqual(len(storage.backup_names()), 3)

    def test_corrupt_file_falls_back_to_newest_backup(self):
        storage = self._storage()
        doc = empty_document()
        doc["events"] = [{"id": "event_ok", "cost": 42.0}]
        storage.save(doc)          # backup #1 created when second save happens
        second = empty_document()
        second["events"] = [{"id": "event_two"}]
        storage.save(second)       # now backups contain revision-1 file
        storage.path.write_text("{not json at all", encoding="utf-8")
        recovered = storage.load()
        self.assertEqual(recovered["events"][0]["id"], "event_ok")

    def test_corrupt_file_without_backups_raises(self):
        storage = self._storage()
        storage.path.write_text("totally not json", encoding="utf-8")
        with self.assertRaises(StoreCorruptError):
            storage.load()

    def test_data_file_must_be_object(self):
        storage = self._storage()
        storage.path.write_text("[1,2,3]", encoding="utf-8")
        with self.assertRaises(StoreCorruptError):
            storage.load()

    def test_save_rejects_wrong_shapes(self):
        storage = self._storage()
        with self.assertRaises(Exception):
            storage.save({"systems": "nope"})

    def test_directory_as_data_file_rejected(self):
        (self.base / "adirectory.json").mkdir()
        with self.assertRaises(PathSafetyError):
            Storage(self.base, "adirectory.json")

    def test_hidden_tmp_files_do_not_leak_into_backups(self):
        storage = self._storage()
        doc = empty_document()
        storage.save(doc)
        storage.save(doc)
        names = storage.backup_names()
        for name in names:
            self.assertFalse(name.startswith("."))


class IdTests(unittest.TestCase):
    def test_prefixed_unique_ids(self):
        ids = {new_id("sys") for _ in range(50)}
        self.assertEqual(len(ids), 50)
        for value in ids:
            self.assertTrue(value.startswith("sys_"))


if __name__ == "__main__":
    unittest.main()
