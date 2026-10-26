"""MCP tool handlers for the home maintenance server."""

from __future__ import annotations

from datetime import date

from . import recurrence
from .recurrence import parse_cost, parse_date
from .storage import Storage, empty_document, new_id

VALID_EVENT_KINDS = ("contractor", "service", "diy", "repair", "inspection")


def _id(item) -> str:
    return item.get("id", "")


def _find(items, target, label):
    for item in items:
        if _id(item) == target:
            return item
    raise ValueError(f"unknown {label}: {target!r}")


class Toolbox:
    """Business logic over a Storage instance; one handler per MCP tool."""

    name = "home-maintenance"

    def __init__(self, storage: Storage, initial: dict | None = None):
        self.storage = storage
        self.doc = storage.load(initial=initial) or empty_document()

    def _write(self) -> None:
        self.storage.save(self.doc)

    def get_due(self, args: dict):
        horizon = args.get("horizon_days", 14)
        if not isinstance(horizon, int) or isinstance(horizon, bool) or not 0 <= horizon <= 365:
            raise ValueError("horizon_days must be an integer between 0 and 365")
        as_of = parse_date(args.get("as_of", date.today().isoformat()))
        out = []
        for task in self.doc["tasks"]:
            last_done = task.get("last_done")
            if last_done is None:
                due = None
                status = "never_done"
            else:
                due = recurrence.next_due(
                    parse_date(last_done), task["interval_days"], task.get("season_months")
                )
                status = recurrence.classify_due(due, as_of, horizon)
            system_name = None
            if task.get("system_id"):
                system_name = _find(self.doc["systems"], task["system_id"], "system").get("name")
            out.append(
                {
                    "task_id": task["id"],
                    "task": task["name"],
                    "interval_days": task["interval_days"],
                    "last_done": last_done,
                    "due_date": recurrence.format_date(due) if due else None,
                    "status": status,
                    "system": system_name,
                    "notes": task.get("notes", ""),
                }
            )
        for doc_record in self.doc["documents"]:
            if not doc_record.get("warranty_until"):
                continue
            until = parse_date(doc_record["warranty_until"])
            status = recurrence.warranty_status(until, as_of, horizon)
            if status in ("expired", "expiring_soon"):
                out.append(
                    {
                        "task_id": None,
                        "task": f"Warranty/inspection: {doc_record['title']}",
                        "interval_days": None,
                        "last_done": None,
                        "due_date": recurrence.format_date(until),
                        "status": status,
                        "system": None,
                        "notes": doc_record.get("notes", ""),
                    }
                )
        order = {"overdue": 0, "due_soon": 1, "never_done": 2, "ok": 3}
        out.sort(key=lambda row: (order.get(row["status"], 9), row.get("due_date") or "9999"))
        return {"as_of": recurrence.format_date(as_of), "horizon_days": horizon, "items": out}

    def add_system(self, args: dict):
        name = str(args.get("name", "")).strip()
        if not name:
            raise ValueError("name is required and must be a non-empty string")
        installed = args.get("installed")
        if installed is not None:
            installed = recurrence.format_date(parse_date(installed))
        system = {
            "id": new_id("sys"),
            "name": name,
            "category": _clean(args.get("category")),
            "location": _clean(args.get("location")),
            "installed": installed,
            "notes": _clean(args.get("notes")),
        }
        self.doc["systems"].append(system)
        self._write()
        return {"message": f"system added: {name}", "system": system}

    def list_systems(self, args: dict):
        return {"count": len(self.doc["systems"]), "systems": self.doc["systems"]}

    def add_task(self, args: dict):
        name = str(args.get("name", "")).strip()
        if not name:
            raise ValueError("name is required and must be a non-empty string")
        interval = args.get("interval_days")
        if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1:
            raise ValueError("interval_days must be an integer of at least 1")
        season = recurrence.normalize_season_months(args.get("season_months"))
        last_done = args.get("last_done")
        if last_done is not None:
            last_done = recurrence.format_date(parse_date(last_done))
        system_id = args.get("system_id")
        if system_id is not None:
            _find(self.doc["systems"], system_id, "system")
        task = {
            "id": new_id("task"),
            "name": name,
            "system_id": system_id,
            "interval_days": interval,
            "last_done": last_done,
            "season_months": season,
            "notes": _clean(args.get("notes")),
        }
        self.doc["tasks"].append(task)
        self._write()
        return {"message": f"task added: {name}", "task": task}

    def list_tasks(self, args: dict):
        return {"count": len(self.doc["tasks"]), "tasks": self.doc["tasks"]}

    def complete_task(self, args: dict):
        task_id = args.get("task_id")
        if not isinstance(task_id, str):
            raise ValueError("task_id is required")
        day = recurrence.format_date(parse_date(args.get("date", date.today().isoformat())))
        task = _find(self.doc["tasks"], task_id, "task")
        task["last_done"] = day
        self._write()
        return {"message": f"task marked done on {day}", "task": task}

    def record_event(self, args: dict):
        day = recurrence.format_date(parse_date(args.get("date", date.today().isoformat())))
        summary = str(args.get("summary", "")).strip()
        if not summary:
            raise ValueError("summary is required and must be a non-empty string")
        kind = args.get("kind", "service")
        if kind not in VALID_EVENT_KINDS:
            raise ValueError(f"kind must be one of: {', '.join(VALID_EVENT_KINDS)}")
        system_id = args.get("system_id")
        if system_id is not None:
            _find(self.doc["systems"], system_id, "system")
        task_id = args.get("task_id")
        task = None
        if task_id is not None:
            task = _find(self.doc["tasks"], task_id, "task")
        cost = parse_cost(args.get("cost"))
        event = {
            "id": new_id("event"),
            "date": day,
            "kind": kind,
            "summary": summary,
            "system_id": system_id,
            "task_id": task_id,
            "contractor": _clean(args.get("contractor")),
            "cost": cost,
            "notes": _clean(args.get("notes")),
        }
        self.doc["events"].append(event)
        if task is not None:
            current = task.get("last_done")
            if current is None or day > current:
                task["last_done"] = day
        self._write()
        return {"message": f"event logged on {day}", "event": event}

    def list_events(self, args: dict):
        events = self.doc["events"]
        if args.get("system_id") is not None:
            events = [e for e in events if e.get("system_id") == args["system_id"]]
        if args.get("kind") is not None:
            if args["kind"] not in VALID_EVENT_KINDS:
                raise ValueError(f"kind must be one of: {', '.join(VALID_EVENT_KINDS)}")
            events = [e for e in events if e.get("kind") == args["kind"]]
        limit = args.get("limit", 50)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise ValueError("limit must be an integer between 1 and 1000")
        events = sorted(events, key=lambda e: e.get("date", ""), reverse=True)[:limit]
        total_cost = sum(e.get("cost") or 0 for e in events)
        return {
            "count": len(events),
            "total_cost": round(total_cost, 2),
            "events": events,
        }

    def add_document(self, args: dict):
        title = str(args.get("title", "")).strip()
        if not title:
            raise ValueError("title is required and must be a non-empty string")
        warranty_until = args.get("warranty_until")
        if warranty_until is not None:
            warranty_until = recurrence.format_date(parse_date(warranty_until))
        system_id = args.get("system_id")
        if system_id is not None:
            _find(self.doc["systems"], system_id, "system")
        record = {
            "id": new_id("doc"),
            "title": title,
            "system_id": system_id,
            "warranty_until": warranty_until,
            "manual_location": _clean(args.get("manual_location")),
            "notes": _clean(args.get("notes")),
        }
        self.doc["documents"].append(record)
        self._write()
        return {"message": f"document noted: {title}", "document": record}

    def list_documents(self, args: dict):
        return {"count": len(self.doc["documents"]), "documents": self.doc["documents"]}


def _clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None
