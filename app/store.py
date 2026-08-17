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
                    samples_json TEXT NOT NULL DEFAULT '[]', external_report_id TEXT,
                    device_serial TEXT, report_date TEXT, timezone TEXT,
                    awake_minutes INTEGER, light_sleep_minutes INTEGER,
                    deep_sleep_minutes INTEGER, rem_sleep_minutes INTEGER,
                    sleep_score REAL, data_status TEXT NOT NULL DEFAULT 'final',
                    stages_json TEXT NOT NULL DEFAULT '[]', received_at TEXT
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
                CREATE TABLE IF NOT EXISTS llm_output (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, entity_id TEXT NOT NULL,
                    content_json TEXT NOT NULL, source TEXT NOT NULL, model TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_llm_output_entity
                    ON llm_output(kind, entity_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS resident_feedback (
                    id TEXT PRIMARY KEY, topic TEXT NOT NULL, message TEXT NOT NULL,
                    summary TEXT NOT NULL, category TEXT NOT NULL,
                    needs_follow_up INTEGER NOT NULL, source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assistant_conversation (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assistant_message (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL, source TEXT NOT NULL,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    context_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES assistant_conversation(id)
                );
                CREATE INDEX IF NOT EXISTS ix_assistant_message_conversation
                    ON assistant_message(conversation_id, created_at);
                CREATE TABLE IF NOT EXISTS assistant_action (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                    message_id TEXT NOT NULL, kind TEXT NOT NULL, label TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES assistant_conversation(id),
                    FOREIGN KEY(message_id) REFERENCES assistant_message(id)
                );
                """
            )
            self._migrate_sleep_summary(db)
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_sleep_report_source "
                "ON sleep_summary(device_serial, external_report_id) "
                "WHERE device_serial IS NOT NULL AND external_report_id IS NOT NULL"
            )
            defaults = {
                "camera_paused": "false", "sleep_alerts_paused": "false",
                "contact_name": "家人", "contact_phone": "",
                "evidence_retention_days": "7",
            }
            db.executemany(
                "INSERT OR IGNORE INTO app_setting(key,value) VALUES (?,?)", defaults.items()
            )

    @staticmethod
    def _migrate_sleep_summary(db: sqlite3.Connection) -> None:
        existing = {
            row["name"] for row in db.execute("PRAGMA table_info(sleep_summary)")
        }
        columns = {
            "external_report_id": "TEXT",
            "device_serial": "TEXT",
            "report_date": "TEXT",
            "timezone": "TEXT",
            "awake_minutes": "INTEGER",
            "light_sleep_minutes": "INTEGER",
            "deep_sleep_minutes": "INTEGER",
            "rem_sleep_minutes": "INTEGER",
            "sleep_score": "REAL",
            "data_status": "TEXT NOT NULL DEFAULT 'final'",
            "stages_json": "TEXT NOT NULL DEFAULT '[]'",
            "received_at": "TEXT",
        }
        for name, definition in columns.items():
            if name not in existing:
                db.execute(f"ALTER TABLE sleep_summary ADD COLUMN {name} {definition}")

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
                    "UPDATE safety_task SET explanation=?,suggestion=?,updated_at=?,"
                    "evidence_url=COALESCE(?,evidence_url) WHERE id=?",
                    (explanation, suggestion, timestamp, evidence_url, existing["id"]),
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
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing_id = None
            if payload.get("device_serial") and payload.get("external_report_id"):
                row = db.execute(
                    "SELECT id FROM sleep_summary WHERE device_serial=? AND external_report_id=?",
                    (payload["device_serial"], payload["external_report_id"]),
                ).fetchone()
                existing_id = row["id"] if row else None
            record = {**payload, "id": existing_id or payload.get("id") or str(uuid4())}
            record["samples_json"] = json.dumps(payload.get("samples", []), ensure_ascii=False)
            record["stages_json"] = json.dumps(payload.get("stages", []), ensure_ascii=False)
            record["received_at"] = now_iso()
            keys = [
                "id", "external_report_id", "device_serial", "report_date", "timezone",
                "sleep_start", "sleep_end", "duration_minutes", "awake_minutes",
                "light_sleep_minutes", "deep_sleep_minutes", "rem_sleep_minutes",
                "sleep_score", "respiratory_rate", "heart_rate", "respiratory_min",
                "respiratory_max", "heart_rate_min", "heart_rate_max", "bed_exit_count",
                "quality", "data_status", "source", "measured_at", "samples_json",
                "stages_json", "received_at",
            ]
            values = {key: record.get(key) for key in keys}
            db.execute(
                f"INSERT INTO sleep_summary({','.join(keys)}) "
                f"VALUES ({','.join(':'+key for key in keys)}) "
                "ON CONFLICT(id) DO UPDATE SET "
                + ",".join(f"{key}=excluded.{key}" for key in keys if key != "id"),
                values,
            )
            row = db.execute("SELECT * FROM sleep_summary WHERE id=?", (record["id"],)).fetchone()
        return self._decode_sleep(dict(row)) if row else record

    def latest_sleep(self) -> dict[str, Any] | None:
        rows = self.sleep_history(1)
        return rows[0] if rows else None

    def sleep_history(self, limit: int = 7) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = [dict(r) for r in db.execute(
                "SELECT * FROM sleep_summary ORDER BY sleep_end DESC LIMIT ?", (limit,)
            )]
        return [self._decode_sleep(row) for row in rows]

    @staticmethod
    def _decode_sleep(record: dict[str, Any]) -> dict[str, Any]:
        result = dict(record)
        result["samples"] = json.loads(result.pop("samples_json", "[]"))
        result["stages"] = json.loads(result.pop("stages_json", "[]"))
        return result

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

    def add_llm_output(
        self, kind: str, entity_id: str, content: dict[str, Any], source: str, model: str
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid4()), "kind": kind, "entity_id": entity_id,
            "content_json": json.dumps(content, ensure_ascii=False),
            "source": source, "model": model, "created_at": now_iso(),
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO llm_output VALUES "
                "(:id,:kind,:entity_id,:content_json,:source,:model,:created_at)",
                record,
            )
        return {**record, "content": content}

    def latest_llm_output(self, kind: str, entity_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM llm_output WHERE kind=? AND entity_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (kind, entity_id),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["content"] = json.loads(result.pop("content_json"))
        return result

    def llm_stats(self) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT source, COUNT(*) AS total FROM llm_output GROUP BY source"
            ).fetchall()
            latest = db.execute(
                "SELECT source,model,created_at FROM llm_output ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        counts = {row["source"]: row["total"] for row in rows}
        return {
            "total": sum(counts.values()),
            "llm": counts.get("llm", 0),
            "template": counts.get("template", 0),
            "latest": dict(latest) if latest else None,
        }

    def create_feedback(
        self, topic: str, message: str, summary: str, category: str,
        needs_follow_up: bool, source: str,
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid4()), "topic": topic, "message": message,
            "summary": summary, "category": category,
            "needs_follow_up": int(needs_follow_up), "source": source,
            "created_at": now_iso(),
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO resident_feedback VALUES "
                "(:id,:topic,:message,:summary,:category,:needs_follow_up,:source,:created_at)",
                record,
            )
        return {**record, "needs_follow_up": needs_follow_up}

    def feedback(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM resident_feedback ORDER BY created_at DESC LIMIT ?", (limit,)
            )]
        for row in rows:
            row["needs_follow_up"] = bool(row["needs_follow_up"])
        return rows

    def create_assistant_conversation(self, title: str) -> dict[str, Any]:
        timestamp = now_iso()
        record = {
            "id": str(uuid4()), "title": title or "与小安的对话",
            "created_at": timestamp, "updated_at": timestamp,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO assistant_conversation VALUES (:id,:title,:created_at,:updated_at)",
                record,
            )
        return record

    def get_assistant_conversation(self, conversation_id: str | None) -> dict[str, Any] | None:
        if not conversation_id:
            return None
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM assistant_conversation WHERE id=?", (conversation_id,)
            ).fetchone()
        return dict(row) if row else None

    def add_assistant_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        source: str,
        sources: list[dict[str, str]] | None = None,
        context_used: list[str] | None = None,
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid4()), "conversation_id": conversation_id, "role": role,
            "content": content, "source": source,
            "sources_json": json.dumps(sources or [], ensure_ascii=False),
            "context_json": json.dumps(context_used or [], ensure_ascii=False),
            "created_at": now_iso(),
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO assistant_message VALUES "
                "(:id,:conversation_id,:role,:content,:source,:sources_json,:context_json,:created_at)",
                record,
            )
            db.execute(
                "UPDATE assistant_conversation SET updated_at=? WHERE id=?",
                (record["created_at"], conversation_id),
            )
        return self._decode_assistant_message(record)

    def assistant_messages(
        self, conversation_id: str, limit: int = 20, with_actions: bool = False
    ) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM (SELECT rowid AS message_order, * FROM assistant_message "
                "WHERE conversation_id=? ORDER BY rowid DESC LIMIT ?) ORDER BY message_order ASC",
                (conversation_id, limit),
            )]
        messages = [self._decode_assistant_message(row) for row in rows]
        if with_actions:
            for message in messages:
                message["actions"] = self.assistant_actions(message["id"])
        return messages

    def create_assistant_action(
        self, conversation_id: str, message_id: str, kind: str, label: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        timestamp = now_iso()
        record = {
            "id": str(uuid4()), "conversation_id": conversation_id,
            "message_id": message_id, "kind": kind, "label": label,
            "payload_json": json.dumps(payload, ensure_ascii=False), "status": "pending",
            "created_at": timestamp, "updated_at": timestamp,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO assistant_action VALUES "
                "(:id,:conversation_id,:message_id,:kind,:label,:payload_json,:status,:created_at,:updated_at)",
                record,
            )
        return self._decode_assistant_action(record)

    def assistant_actions(self, message_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM assistant_action WHERE message_id=? ORDER BY created_at", (message_id,)
            )]
        return [self._decode_assistant_action(row) for row in rows]

    def get_assistant_action(self, action_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM assistant_action WHERE id=?", (action_id,)).fetchone()
        return self._decode_assistant_action(dict(row)) if row else None

    def update_assistant_action(self, action_id: str, status: str) -> dict[str, Any] | None:
        with self._connect() as db:
            db.execute(
                "UPDATE assistant_action SET status=?,updated_at=? WHERE id=?",
                (status, now_iso(), action_id),
            )
        return self.get_assistant_action(action_id)

    @staticmethod
    def _decode_assistant_message(record: dict[str, Any]) -> dict[str, Any]:
        result = dict(record)
        result.pop("message_order", None)
        result["sources"] = json.loads(result.pop("sources_json", "[]"))
        result["context_used"] = json.loads(result.pop("context_json", "[]"))
        result.setdefault("actions", [])
        return result

    @staticmethod
    def _decode_assistant_action(record: dict[str, Any]) -> dict[str, Any]:
        result = dict(record)
        result["payload"] = json.loads(result.pop("payload_json", "{}"))
        return result
