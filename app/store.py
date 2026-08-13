"""Small SQLite product store with explicit JSON boundaries."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ProductStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS safety_task (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, location TEXT NOT NULL,
                    explanation TEXT NOT NULL, suggestion TEXT NOT NULL,
                    status TEXT NOT NULL, source TEXT NOT NULL, evidence_url TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS safety_check (
                    id TEXT PRIMARY KEY, result TEXT NOT NULL, source TEXT NOT NULL,
                    detail TEXT NOT NULL, evidence_url TEXT, occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sleep_summary (
                    id TEXT PRIMARY KEY, sleep_start TEXT NOT NULL, sleep_end TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL, respiratory_rate REAL,
                    heart_rate REAL, respiratory_min REAL, respiratory_max REAL,
                    heart_rate_min REAL, heart_rate_max REAL, bed_exit_count INTEGER,
                    quality TEXT NOT NULL, source TEXT NOT NULL, measured_at TEXT NOT NULL,
                    samples_json TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS help_request (
                    id TEXT PRIMARY KEY, request_type TEXT NOT NULL, message TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS vision_sample (
                    id TEXT PRIMARY KEY, file_path TEXT NOT NULL, annotation_json TEXT NOT NULL,
                    source TEXT NOT NULL, created_at TEXT NOT NULL
                );
                """
            )
            defaults = {
                "camera_paused": "false", "sleep_alerts_paused": "false",
                "contact_name": "家人", "contact_phone": "",
                "evidence_retention_days": "7",
            }
            db.executemany(
                "INSERT OR IGNORE INTO app_setting(key,value) VALUES (?,?)", defaults.items()
            )

    def settings(self) -> dict[str, str]:
        with self._connect() as db:
            return {r["key"]: r["value"] for r in db.execute("SELECT key,value FROM app_setting")}

    def update_settings(self, values: dict[str, str]) -> dict[str, str]:
        with self._connect() as db:
            db.executemany(
                "INSERT INTO app_setting(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", values.items()
            )
        return self.settings()

    def latest_task(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM safety_task WHERE status NOT IN ('resolved','dismissed') "
                "ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def recent_checks(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM safety_check ORDER BY occurred_at DESC LIMIT ?", (limit,)
            )]

    def add_safety_check(
        self, result: str, source: str, detail: str, evidence_url: str | None = None
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid4()), "result": result, "source": source, "detail": detail,
            "evidence_url": evidence_url, "occurred_at": now_iso(),
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO safety_check VALUES (:id,:result,:source,:detail,:evidence_url,:occurred_at)",
                record,
            )
        return record

    def create_safety_task(
        self, title: str, location: str, explanation: str, suggestion: str,
        source: str, evidence_url: str | None = None,
    ) -> dict[str, Any]:
        existing = self.latest_task()
        timestamp = now_iso()
        if existing and existing["title"] == title and existing["location"] == location:
            with self._connect() as db:
                db.execute(
                    "UPDATE safety_task SET updated_at=?,evidence_url=COALESCE(?,evidence_url) WHERE id=?",
                    (timestamp, evidence_url, existing["id"]),
                )
            return self.latest_task() or existing
        record = {
            "id": str(uuid4()), "title": title, "location": location,
            "explanation": explanation, "suggestion": suggestion, "status": "open",
            "source": source, "evidence_url": evidence_url,
            "created_at": timestamp, "updated_at": timestamp,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO safety_task VALUES (:id,:title,:location,:explanation,:suggestion,"
                ":status,:source,:evidence_url,:created_at,:updated_at)", record,
            )
        return record

    def act_on_task(self, task_id: str, action: str) -> dict[str, Any] | None:
        mapping = {
            "done": "rescan_pending", "later": "deferred", "not_risk": "dismissed",
            "pause": "paused", "need_help": "waiting_family",
        }
        with self._connect() as db:
            db.execute(
                "UPDATE safety_task SET status=?,updated_at=? WHERE id=?",
                (mapping[action], now_iso(), task_id),
            )
            row = db.execute("SELECT * FROM safety_task WHERE id=?", (task_id,)).fetchone()
        if row and action == "need_help":
            self.create_help_request("safety", f"需要帮忙处理：{row['location']}的{row['title']}")
        return dict(row) if row else None

    def resolve_pending_task(self) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE safety_task SET status='resolved',updated_at=? WHERE status='rescan_pending'",
                (now_iso(),),
            )

    def add_sleep(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = {**payload, "id": payload.get("id") or str(uuid4())}
        record["samples_json"] = json.dumps(payload.get("samples", []), ensure_ascii=False)
        keys = [
            "id", "sleep_start", "sleep_end", "duration_minutes", "respiratory_rate",
            "heart_rate", "respiratory_min", "respiratory_max", "heart_rate_min",
            "heart_rate_max", "bed_exit_count", "quality", "source", "measured_at",
            "samples_json",
        ]
        values = {key: record.get(key) for key in keys}
        with self._connect() as db:
            db.execute(
                f"INSERT OR REPLACE INTO sleep_summary({','.join(keys)}) "
                f"VALUES ({','.join(':'+key for key in keys)})", values,
            )
        return self.latest_sleep() or record

    def latest_sleep(self) -> dict[str, Any] | None:
        rows = self.sleep_history(1)
        return rows[0] if rows else None

    def sleep_history(self, limit: int = 7) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = [dict(r) for r in db.execute(
                "SELECT * FROM sleep_summary ORDER BY sleep_end DESC LIMIT ?", (limit,)
            )]
        for row in rows:
            row["samples"] = json.loads(row.pop("samples_json", "[]"))
        return rows

    def create_help_request(self, request_type: str, message: str) -> dict[str, Any]:
        timestamp = now_iso()
        record = {
            "id": str(uuid4()), "request_type": request_type, "message": message,
            "status": "new", "created_at": timestamp, "updated_at": timestamp,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO help_request VALUES (:id,:request_type,:message,:status,:created_at,:updated_at)",
                record,
            )
        return record

    def help_requests(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM help_request ORDER BY created_at DESC LIMIT ?", (limit,)
            )]

    def update_help(self, request_id: str, status: str) -> dict[str, Any] | None:
        with self._connect() as db:
            db.execute(
                "UPDATE help_request SET status=?,updated_at=? WHERE id=?",
                (status, now_iso(), request_id),
            )
            row = db.execute("SELECT * FROM help_request WHERE id=?", (request_id,)).fetchone()
        return dict(row) if row else None

    def add_vision_sample(self, path: str, annotation: dict[str, Any], source: str) -> str:
        sample_id = str(uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO vision_sample VALUES (?,?,?,?,?)",
                (sample_id, path, json.dumps(annotation, ensure_ascii=False), source, now_iso()),
            )
        return sample_id
