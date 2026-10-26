"""JSON storage with path safety and automatic backups.

All data lives in a single JSON file.  Every path the caller supplies is
resolved and must stay inside a base directory, which blocks traversal
escapes such as ``../../etc/passwd`` or absolute paths outside the base.
Before each save, the previous contents are copied into a ``backups``
subfolder with a timestamped name; the oldest backups are pruned.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

BACKUP_DIRNAME = "backups"
DEFAULT_KEEP = 10


class StorageError(Exception):
    pass


class PathSafetyError(StorageError):
    pass


class StoreCorruptError(StorageError):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def resolve_within(base_dir, raw_path) -> Path:
    """Return ``raw_path`` resolved, guaranteed to stay inside ``base_dir``."""
    try:
        base = Path(base_dir).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise PathSafetyError(f"base directory does not exist: {base_dir}") from exc
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise PathSafetyError("data path must be a non-empty string")
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    if ".." in candidate.parts:
        raise PathSafetyError("path traversal is not allowed")
    resolved = candidate.resolve(strict=False)
    if resolved != base and base not in resolved.parents:
        raise PathSafetyError("data file must live inside the base directory")
    if resolved.suffix.lower() != ".json":
        raise PathSafetyError("data file must have a .json extension")
    if resolved.is_dir():
        raise PathSafetyError("data path points to a directory")
    return resolved


def empty_document() -> dict:
    return {"systems": [], "tasks": [], "events": [], "documents": [], "revision": 0}


class Storage:
    def __init__(self, base_dir, raw_path, keep_backups: int = DEFAULT_KEEP):
        self.base_dir = Path(base_dir).expanduser().resolve(strict=True)
        self.path = resolve_within(base_dir, raw_path)
        self.backup_dir = self.path.parent / BACKUP_DIRNAME
        self.keep_backups = max(1, int(keep_backups))

    def backup_names(self):
        if not self.backup_dir.is_dir():
            return []
        return sorted(p.name for p in self.backup_dir.glob("*.json"))

    def load(self, initial: dict | None = None) -> dict:
        """Load the data file, falling back to the newest backup if it is corrupt."""
        if not self.path.exists():
            return dict(initial) if initial is not None else empty_document()
        try:
            return self._parse(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            for name in reversed(self.backup_names()):
                try:
                    data = self._parse((self.backup_dir / name).read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                    continue
                try:
                    self.save(data, doc_already_validated=True)
                    return data
                except OSError:
                    return data
            raise StoreCorruptError(
                f"data file {self.path.name} is corrupt and no valid backup was found"
            )

    def _parse(self, text: str) -> dict:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise StoreCorruptError("data file must contain a JSON object")
        for key in ("systems", "tasks", "events", "documents"):
            data.setdefault(key, [])
            if not isinstance(data[key], list):
                raise StoreCorruptError(f"data field {key!r} must be a list")
        data.setdefault("revision", 0)
        if not isinstance(data.get("revision"), int):
            data["revision"] = 0
        return data

    def save(self, doc: dict, doc_already_validated: bool = False) -> None:
        if not doc_already_validated:
            for key in ("systems", "tasks", "events", "documents"):
                if not isinstance(doc.get(key), list):
                    raise StorageError(f"data field {key!r} must be a list")
        doc["revision"] = int(doc.get("revision", 0)) + 1
        text = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._make_backup()
        tmp = self.path.with_name(self.path.name + f".tmp-{os.getpid()}")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(tmp, self.path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    def _make_backup(self) -> None:
        if not self.path.exists():
            return
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = self.backup_dir / f"{self.path.stem}-{stamp}.json"
        shutil.copy2(self.path, target)
        names = self.backup_names()
        for stale in names[: max(0, len(names) - self.keep_backups)]:
            try:
                (self.backup_dir / stale).unlink()
            except OSError:
                pass
