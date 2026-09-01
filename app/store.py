"""Small SQLite product store with explicit JSON boundaries."""

import json
import sqlite3
from datetime import datetime, time, timedelta
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
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, remind_at TEXT
                );
                CREATE TABLE IF NOT EXISTS safety_check (
                    id TEXT PRIMARY KEY, result TEXT NOT NULL, source TEXT NOT NULL,
                    detail TEXT NOT NULL, evidence_url TEXT, occurred_at TEXT NOT NULL,
                    analysis_json TEXT NOT NULL DEFAULT '{}'
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
                    stages_json TEXT NOT NULL DEFAULT '[]', received_at TEXT,
                    updated_at TEXT, demo_dataset_id TEXT, bed_exit_status TEXT
                );
                CREATE TABLE IF NOT EXISTS sleep_bed_event (
                    id TEXT PRIMARY KEY, sleep_report_id TEXT, device_serial TEXT,
                    event_type TEXT NOT NULL, device_time TEXT NOT NULL,
                    occurred_at TEXT NOT NULL, source TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    UNIQUE(device_serial, occurred_at, event_type)
                );
                CREATE TABLE IF NOT EXISTS sleep_night_awakening (
                    id TEXT PRIMARY KEY, sleep_report_id TEXT,
                    demo_dataset_id TEXT, source TEXT NOT NULL,
                    detected_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                    state TEXT NOT NULL, attention TEXT NOT NULL,
                    snapshot_status TEXT NOT NULL, sleep_session_ended INTEGER NOT NULL,
                    baseline_json TEXT NOT NULL, reasons_json TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL, guidance_json TEXT NOT NULL,
                    message TEXT NOT NULL, disclaimer TEXT NOT NULL,
                    algorithm_version TEXT NOT NULL, created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_sleep_night_awakening_latest
                    ON sleep_night_awakening(source, detected_at DESC);
                CREATE TABLE IF NOT EXISTS sleep_sync_run (
                    id TEXT PRIMARY KEY, target_date TEXT NOT NULL,
                    source TEXT NOT NULL, status TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT,
                    error_code TEXT, message TEXT
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
                CREATE TABLE IF NOT EXISTS resident_profile_fact (
                    id TEXT PRIMARY KEY, fact_type TEXT NOT NULL,
                    value_json TEXT NOT NULL, display_text TEXT NOT NULL,
                    status TEXT NOT NULL, source TEXT NOT NULL, source_ref TEXT,
                    confidence REAL, consented_at TEXT, expires_at TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_profile_fact_status
                    ON resident_profile_fact(status, updated_at DESC);
                CREATE TABLE IF NOT EXISTS proactive_event (
                    id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
                    title TEXT NOT NULL, message TEXT NOT NULL, reason TEXT NOT NULL,
                    source TEXT NOT NULL, source_ref TEXT, priority TEXT NOT NULL,
                    status TEXT NOT NULL, conversation_id TEXT,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    response_json TEXT NOT NULL DEFAULT '{}',
                    remind_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(event_type, source, source_ref)
                );
                CREATE INDEX IF NOT EXISTS ix_proactive_event_status
                    ON proactive_event(status, created_at DESC);
                CREATE TABLE IF NOT EXISTS intervention_session (
                    id TEXT PRIMARY KEY, event_id TEXT, intervention_id TEXT NOT NULL,
                    title TEXT NOT NULL, status TEXT NOT NULL, helpful INTEGER,
                    feedback TEXT, started_at TEXT NOT NULL, completed_at TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._migrate_sleep_summary(db)
            self._migrate_safety_check(db)
            self._migrate_safety_task(db)
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_sleep_report_source "
                "ON sleep_summary(device_serial, external_report_id) "
                "WHERE device_serial IS NOT NULL AND external_report_id IS NOT NULL"
            )
            defaults = {
                "camera_paused": "false", "sleep_alerts_paused": "false",
                "contact_name": "家人", "contact_phone": "",
                "evidence_retention_days": "7",
                "proactive_care_paused": "false",
                "psychological_care_enabled": "true",
                "quiet_start": "21:30", "quiet_end": "08:00",
                "daily_proactive_limit": "2",
                "assistant_device_control_consent": "unset",
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
            "updated_at": "TEXT",
            "demo_dataset_id": "TEXT",
            "bed_exit_status": "TEXT",
        }
        for name, definition in columns.items():
            if name not in existing:
                db.execute(f"ALTER TABLE sleep_summary ADD COLUMN {name} {definition}")

    @staticmethod
    def _migrate_safety_check(db: sqlite3.Connection) -> None:
        existing = {row["name"] for row in db.execute("PRAGMA table_info(safety_check)")}
        if "analysis_json" not in existing:
            db.execute(
                "ALTER TABLE safety_check ADD COLUMN analysis_json "
                "TEXT NOT NULL DEFAULT '{}'"
            )

    @staticmethod
    def _migrate_safety_task(db: sqlite3.Connection) -> None:
        existing = {row["name"] for row in db.execute("PRAGMA table_info(safety_task)")}
        if "remind_at" not in existing:
            db.execute("ALTER TABLE safety_task ADD COLUMN remind_at TEXT")

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

    def latest_task(self, include_deferred: bool = False) -> dict[str, Any] | None:
        with self._connect() as db:
            if include_deferred:
                where = "status NOT IN ('resolved','dismissed')"
                parameters: tuple[str, ...] = ()
            else:
                where = (
                    "status NOT IN ('resolved','dismissed') "
                    "AND (status!='deferred' OR remind_at IS NULL OR remind_at<=?)"
                )
                parameters = (now_iso(),)
            row = db.execute(
                f"SELECT * FROM safety_task WHERE {where} ORDER BY updated_at DESC LIMIT 1",
                parameters,
            ).fetchone()
        return dict(row) if row else None

    def recent_checks(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM safety_check ORDER BY occurred_at DESC,rowid DESC LIMIT ?", (limit,)
            )]

    def safety_check(self, check_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM safety_check WHERE id=?", (check_id,)).fetchone()
        return dict(row) if row else None

    def add_safety_check(
        self,
        result: str,
        source: str,
        detail: str,
        evidence_url: str | None = None,
        analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid4()), "result": result, "source": source, "detail": detail,
            "evidence_url": evidence_url, "occurred_at": now_iso(),
            "analysis_json": json.dumps(analysis or {}, ensure_ascii=False),
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO safety_check(id,result,source,detail,evidence_url,occurred_at,analysis_json) "
                "VALUES (:id,:result,:source,:detail,:evidence_url,:occurred_at,:analysis_json)",
                record,
            )
        return record

    def create_safety_task(
        self, title: str, location: str, explanation: str, suggestion: str,
        source: str, evidence_url: str | None = None,
    ) -> dict[str, Any]:
        existing = self.latest_task(include_deferred=True)
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
            "remind_at": None,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO safety_task(id,title,location,explanation,suggestion,status,source,"
                "evidence_url,created_at,updated_at,remind_at) VALUES (:id,:title,:location,"
                ":explanation,:suggestion,:status,:source,:evidence_url,:created_at,:updated_at,"
                ":remind_at)", record,
            )
        return record

    def act_on_task(self, task_id: str, action: str) -> dict[str, Any] | None:
        mapping = {
            "done": "rescan_pending", "later": "deferred", "not_risk": "dismissed",
            "pause": "paused", "need_help": "waiting_family",
        }
        remind_at = (
            (datetime.now().astimezone() + timedelta(minutes=30)).isoformat(timespec="seconds")
            if action == "later"
            else None
        )
        with self._connect() as db:
            db.execute(
                "UPDATE safety_task SET status=?,updated_at=?,remind_at=? WHERE id=?",
                (mapping[action], now_iso(), remind_at, task_id),
            )
            row = db.execute("SELECT * FROM safety_task WHERE id=?", (task_id,)).fetchone()
        if row and action == "need_help":
            self.create_help_request("safety", f"需要帮忙处理：{row['location']}的{row['title']}")
        return dict(row) if row else None

    def update_safety_task(
        self,
        task_id: str,
        title: str,
        explanation: str,
        suggestion: str,
        status: str = "open",
    ) -> dict[str, Any] | None:
        with self._connect() as db:
            db.execute(
                "UPDATE safety_task SET title=?,explanation=?,suggestion=?,status=?,updated_at=?,"
                "remind_at=NULL "
                "WHERE id=?",
                (title, explanation, suggestion, status, now_iso(), task_id),
            )
            row = db.execute("SELECT * FROM safety_task WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def resolve_pending_task(self) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE safety_task SET status='resolved',updated_at=? WHERE status='rescan_pending'",
                (now_iso(),),
            )

    def resolve_safety_task(self, task_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE safety_task SET status='resolved',updated_at=? WHERE id=?",
                (now_iso(), task_id),
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
            record["data_status"] = payload.get("data_status") or "final"
            record["report_date"] = payload.get("report_date") or str(
                payload.get("sleep_end", "")
            )[:10]
            record["samples_json"] = json.dumps(payload.get("samples", []), ensure_ascii=False)
            record["stages_json"] = json.dumps(payload.get("stages", []), ensure_ascii=False)
            record["received_at"] = now_iso()
            record["updated_at"] = record["received_at"]
            keys = [
                "id", "external_report_id", "device_serial", "report_date", "timezone",
                "sleep_start", "sleep_end", "duration_minutes", "awake_minutes",
                "light_sleep_minutes", "deep_sleep_minutes", "rem_sleep_minutes",
                "sleep_score", "respiratory_rate", "heart_rate", "respiratory_min",
                "respiratory_max", "heart_rate_min", "heart_rate_max", "bed_exit_count",
                "quality", "data_status", "source", "measured_at", "samples_json",
                "stages_json", "received_at", "updated_at", "demo_dataset_id",
                "bed_exit_status",
            ]
            values = {key: record.get(key) for key in keys}
            db.execute(
                f"INSERT INTO sleep_summary({','.join(keys)}) "
                f"VALUES ({','.join(':'+key for key in keys)}) "
                "ON CONFLICT(id) DO UPDATE SET "
                + ",".join(
                    (
                        "received_at=COALESCE(sleep_summary.received_at,excluded.received_at)"
                        if key == "received_at"
                        else f"{key}=excluded.{key}"
                    )
                    for key in keys
                    if key != "id"
                ),
                values,
            )
            row = db.execute("SELECT * FROM sleep_summary WHERE id=?", (record["id"],)).fetchone()
        return self._decode_sleep(dict(row)) if row else record

    def latest_sleep(self) -> dict[str, Any] | None:
        rows = self.sleep_history(1)
        return rows[0] if rows else None

    def sleep_history(
        self,
        limit: int = 7,
        *,
        source: str | None = None,
        demo_dataset_id: str | None = None,
        exclude_demo: bool = False,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        values: list[Any] = []
        if source is not None:
            conditions.append("source=?")
            values.append(source)
        if demo_dataset_id is not None:
            conditions.append("demo_dataset_id=?")
            values.append(demo_dataset_id)
        if exclude_demo:
            conditions.append("source!='demo_generated'")
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        values.append(limit)
        with self._connect() as db:
            rows = [dict(r) for r in db.execute(
                f"SELECT * FROM sleep_summary{where} ORDER BY sleep_end DESC LIMIT ?",
                values,
            )]
        return [self._decode_sleep(row) for row in rows]

    def sleep_report_history(self, limit: int = 15) -> list[dict[str, Any]]:
        """Return one coherent source cohort so demo and device data never mix."""

        latest = self.latest_sleep()
        if latest is None:
            return []
        if latest.get("source") == "demo_generated":
            return self.sleep_history(
                limit,
                source="demo_generated",
                demo_dataset_id=latest.get("demo_dataset_id"),
            )
        return self.sleep_history(limit, exclude_demo=True)

    def delete_demo_sleep(self, dataset_id: str | None = None) -> int:
        with self._connect() as db:
            if dataset_id:
                rows = db.execute(
                    "SELECT id FROM sleep_summary WHERE source='demo_generated' "
                    "AND demo_dataset_id=?",
                    (dataset_id,),
                ).fetchall()
                result = db.execute(
                    "DELETE FROM sleep_summary WHERE source='demo_generated' "
                    "AND demo_dataset_id=?",
                    (dataset_id,),
                )
                db.execute(
                    "DELETE FROM sleep_night_awakening WHERE source='demo_generated' "
                    "AND demo_dataset_id=?",
                    (dataset_id,),
                )
            else:
                rows = db.execute(
                    "SELECT id FROM sleep_summary WHERE source='demo_generated'"
                ).fetchall()
                result = db.execute(
                    "DELETE FROM sleep_summary WHERE source='demo_generated'"
                )
                db.execute(
                    "DELETE FROM sleep_night_awakening WHERE source='demo_generated'"
                )
            ids = [row["id"] for row in rows]
            if ids:
                db.executemany(
                    "DELETE FROM llm_output WHERE kind='sleep' AND entity_id=?",
                    ((item,) for item in ids),
                )
        return int(result.rowcount)

    def start_sleep_sync(self, target_date: str, source: str) -> str:
        run_id = str(uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO sleep_sync_run(id,target_date,source,status,started_at) "
                "VALUES (?,?,?,'running',?)",
                (run_id, target_date, source, now_iso()),
            )
        return run_id

    def finish_sleep_sync(
        self,
        run_id: str,
        status: str,
        message: str,
        error_code: str | None = None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE sleep_sync_run SET status=?,finished_at=?,error_code=?,message=? "
                "WHERE id=?",
                (status, now_iso(), error_code, message[:300], run_id),
            )

    def latest_sleep_sync(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM sleep_sync_run ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def replace_sleep_bed_events(
        self,
        report_id: str,
        device_serial: str,
        events: list[dict[str, str]],
    ) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM sleep_bed_event WHERE sleep_report_id=?", (report_id,))
            db.executemany(
                "INSERT OR IGNORE INTO sleep_bed_event("
                "id,sleep_report_id,device_serial,event_type,device_time,occurred_at,source,received_at"
                ") VALUES (?,?,?,?,?,?,?,?)",
                (
                    (
                        str(uuid4()), report_id, device_serial, item["event_type"],
                        item["device_time"], item["occurred_at"],
                        "ezviz_sleep_assistant", now_iso(),
                    )
                    for item in events
                ),
            )

    def add_night_awakening(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist one assessment snapshot; demo activation is idempotent per dataset."""

        dataset_id = payload.get("demo_dataset_id")
        source = payload["event"]["source"]
        with self._connect() as db:
            if source == "demo_generated" and dataset_id:
                existing = db.execute(
                    "SELECT * FROM sleep_night_awakening "
                    "WHERE source='demo_generated' AND demo_dataset_id=? "
                    "ORDER BY detected_at DESC LIMIT 1",
                    (dataset_id,),
                ).fetchone()
                if existing:
                    return self._decode_night_awakening(dict(existing))

            record = {
                "id": str(uuid4()),
                "sleep_report_id": payload.get("sleep_report_id"),
                "demo_dataset_id": dataset_id,
                "source": source,
                "detected_at": payload["event"]["detected_at"],
                "expires_at": payload["expires_at"],
                "state": payload["state"],
                "attention": payload["attention"],
                "snapshot_status": payload["snapshot_status"],
                "sleep_session_ended": int(bool(payload["sleep_session_ended"])),
                "baseline_json": json.dumps(payload["baseline"], ensure_ascii=False),
                "reasons_json": json.dumps(payload["reasons"], ensure_ascii=False),
                "reason_codes_json": json.dumps(
                    payload.get("reason_codes", []), ensure_ascii=False
                ),
                "guidance_json": json.dumps(payload["guidance"], ensure_ascii=False),
                "message": payload["message"],
                "disclaimer": payload["disclaimer"],
                "algorithm_version": payload["algorithm_version"],
                "created_at": now_iso(),
                "resolved_at": payload.get("resolved_at"),
            }
            db.execute(
                "INSERT INTO sleep_night_awakening("
                + ",".join(record)
                + ") VALUES ("
                + ",".join(f":{key}" for key in record)
                + ")",
                record,
            )
        return self.night_awakening_by_id(record["id"]) or payload

    def night_awakening_by_id(self, record_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM sleep_night_awakening WHERE id=?", (record_id,)
            ).fetchone()
        return self._decode_night_awakening(dict(row)) if row else None

    def latest_night_awakening(
        self, *, source: str, demo_dataset_id: str | None = None
    ) -> dict[str, Any] | None:
        conditions = ["source=?"]
        values: list[Any] = [source]
        if source == "demo_generated":
            conditions.append("demo_dataset_id=?")
            values.append(demo_dataset_id)
        else:
            conditions.append("demo_dataset_id IS NULL")
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM sleep_night_awakening WHERE "
                + " AND ".join(conditions)
                + " ORDER BY detected_at DESC LIMIT 1",
                values,
            ).fetchone()
            if not row:
                return None
            record = dict(row)
            if record["state"] == "active":
                expires_at = datetime.fromisoformat(record["expires_at"])
                if datetime.now().astimezone() >= expires_at:
                    resolved_at = record["expires_at"]
                    db.execute(
                        "UPDATE sleep_night_awakening SET state='resolved',resolved_at=? "
                        "WHERE id=?",
                        (resolved_at, record["id"]),
                    )
                    record["state"] = "resolved"
                    record["resolved_at"] = resolved_at
        return self._decode_night_awakening(record)

    def resolve_night_awakening(
        self, *, source: str, demo_dataset_id: str | None = None
    ) -> dict[str, Any] | None:
        latest = self.latest_night_awakening(
            source=source, demo_dataset_id=demo_dataset_id
        )
        if latest is None:
            return None
        resolved_at = now_iso()
        with self._connect() as db:
            db.execute(
                "UPDATE sleep_night_awakening SET state='resolved',resolved_at=? WHERE id=?",
                (resolved_at, latest["id"]),
            )
        return self.night_awakening_by_id(latest["id"])

    def delete_demo_night_awakening(self, dataset_id: str) -> int:
        with self._connect() as db:
            result = db.execute(
                "DELETE FROM sleep_night_awakening "
                "WHERE source='demo_generated' AND demo_dataset_id=?",
                (dataset_id,),
            )
        return int(result.rowcount)

    @staticmethod
    def _decode_night_awakening(record: dict[str, Any]) -> dict[str, Any]:
        result = dict(record)
        result["sleep_session_ended"] = bool(result["sleep_session_ended"])
        result["baseline"] = json.loads(result.pop("baseline_json"))
        result["reasons"] = json.loads(result.pop("reasons_json"))
        result["reason_codes"] = json.loads(result.pop("reason_codes_json"))
        result["guidance"] = json.loads(result.pop("guidance_json"))
        result["event"] = {
            "type": "out_of_bed",
            "detected_at": result["detected_at"],
            "source": result["source"],
            "reliable": result["attention"] != "insufficient"
            or "event_unreliable" not in result["reason_codes"],
        }
        return result

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

    def create_profile_fact(
        self,
        fact_type: str,
        value: dict[str, Any],
        display_text: str,
        source: str,
        source_ref: str | None = None,
        confidence: float | None = None,
        status: str = "candidate",
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        """Create an auditable profile fact without silently confirming it."""

        with self._connect() as db:
            existing = db.execute(
                "SELECT * FROM resident_profile_fact WHERE fact_type=? AND display_text=? "
                "AND status IN ('candidate','confirmed') ORDER BY updated_at DESC LIMIT 1",
                (fact_type, display_text),
            ).fetchone()
        if existing:
            return self._decode_profile_fact(dict(existing))
        timestamp = now_iso()
        record = {
            "id": str(uuid4()), "fact_type": fact_type,
            "value_json": json.dumps(value, ensure_ascii=False),
            "display_text": display_text, "status": status, "source": source,
            "source_ref": source_ref, "confidence": confidence,
            "consented_at": timestamp if status == "confirmed" else None,
            "expires_at": expires_at, "created_at": timestamp, "updated_at": timestamp,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO resident_profile_fact VALUES "
                "(:id,:fact_type,:value_json,:display_text,:status,:source,:source_ref,"
                ":confidence,:consented_at,:expires_at,:created_at,:updated_at)",
                record,
            )
        return self._decode_profile_fact(record)

    def profile_facts(
        self, statuses: tuple[str, ...] = ("confirmed",), limit: int = 50
    ) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in statuses)
        with self._connect() as db:
            rows = [dict(row) for row in db.execute(
                f"SELECT * FROM resident_profile_fact WHERE status IN ({placeholders}) "
                "AND (expires_at IS NULL OR expires_at>?) ORDER BY updated_at DESC LIMIT ?",
                (*statuses, now_iso(), limit),
            )]
        return [self._decode_profile_fact(row) for row in rows]

    def get_profile_fact(self, fact_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM resident_profile_fact WHERE id=?", (fact_id,)
            ).fetchone()
        return self._decode_profile_fact(dict(row)) if row else None

    def update_profile_fact_status(
        self, fact_id: str, status: str
    ) -> dict[str, Any] | None:
        timestamp = now_iso()
        with self._connect() as db:
            db.execute(
                "UPDATE resident_profile_fact SET status=?,consented_at=?,updated_at=? WHERE id=?",
                (status, timestamp if status == "confirmed" else None, timestamp, fact_id),
            )
        return self.get_profile_fact(fact_id)

    def delete_profile_fact(self, fact_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM resident_profile_fact WHERE id=?", (fact_id,))
        return cursor.rowcount > 0

    def expire_profile_facts_by_type(self, fact_type: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE resident_profile_fact SET status='expired',consented_at=NULL,"
                "updated_at=? WHERE fact_type=? AND status IN ('confirmed','inferred')",
                (now_iso(), fact_type),
            )

    def create_proactive_event(
        self,
        event_type: str,
        title: str,
        message: str,
        reason: str,
        source: str,
        source_ref: str | None,
        priority: str = "normal",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        settings = self.settings()
        if settings.get("proactive_care_paused") == "true":
            return None
        if event_type == "sleep_change" and settings.get("sleep_alerts_paused") == "true":
            return None
        with self._connect() as db:
            if source_ref:
                existing = db.execute(
                    "SELECT * FROM proactive_event WHERE event_type=? AND source=? AND source_ref=?",
                    (event_type, source, source_ref),
                ).fetchone()
                if existing:
                    return self._decode_proactive_event(dict(existing))
            limit = int(settings.get("daily_proactive_limit", "2"))
            today = datetime.now().astimezone().date().isoformat()
            count = db.execute(
                "SELECT COUNT(*) AS total FROM proactive_event WHERE substr(created_at,1,10)=?",
                (today,),
            ).fetchone()["total"]
            if count >= limit and priority not in {"high", "urgent"}:
                return None
        remind_at = None
        if priority not in {"high", "urgent"}:
            now = datetime.now().astimezone()
            quiet_start = time.fromisoformat(settings.get("quiet_start", "21:30"))
            quiet_end = time.fromisoformat(settings.get("quiet_end", "08:00"))
            if quiet_start <= quiet_end:
                in_quiet = quiet_start <= now.time() < quiet_end
                end_date = now.date()
            else:
                in_quiet = now.time() >= quiet_start or now.time() < quiet_end
                end_date = now.date() + timedelta(days=1) if now.time() >= quiet_start else now.date()
            if in_quiet:
                remind_at = datetime.combine(
                    end_date, quiet_end, tzinfo=now.tzinfo
                ).isoformat(timespec="seconds")
        timestamp = now_iso()
        record = {
            "id": str(uuid4()), "event_type": event_type, "title": title,
            "message": message, "reason": reason, "source": source,
            "source_ref": source_ref, "priority": priority, "status": "pending",
            "conversation_id": None,
            "context_json": json.dumps(context or {}, ensure_ascii=False),
            "response_json": "{}", "remind_at": remind_at,
            "created_at": timestamp, "updated_at": timestamp,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO proactive_event VALUES "
                "(:id,:event_type,:title,:message,:reason,:source,:source_ref,:priority,"
                ":status,:conversation_id,:context_json,:response_json,:remind_at,"
                ":created_at,:updated_at)",
                record,
            )
        return self._decode_proactive_event(record)

    def latest_proactive_event(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM proactive_event WHERE status IN ('pending','engaged','later') "
                "AND (remind_at IS NULL OR remind_at<=?) ORDER BY "
                "CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, "
                "created_at DESC LIMIT 1",
                (now_iso(),),
            ).fetchone()
        return self._decode_proactive_event(dict(row)) if row else None

    def proactive_events(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM proactive_event ORDER BY created_at DESC LIMIT ?", (limit,)
            )]
        return [self._decode_proactive_event(row) for row in rows]

    def get_proactive_event(self, event_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM proactive_event WHERE id=?", (event_id,)).fetchone()
        return self._decode_proactive_event(dict(row)) if row else None

    def proactive_event_for_conversation(
        self, conversation_id: str
    ) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM proactive_event WHERE conversation_id=? "
                "ORDER BY updated_at DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        return self._decode_proactive_event(dict(row)) if row else None

    def update_proactive_event(
        self,
        event_id: str,
        status: str,
        response: dict[str, Any] | None = None,
        conversation_id: str | None = None,
        remind_at: str | None = None,
    ) -> dict[str, Any] | None:
        with self._connect() as db:
            db.execute(
                "UPDATE proactive_event SET status=?,response_json=?,"
                "conversation_id=COALESCE(?,conversation_id),remind_at=?,updated_at=? WHERE id=?",
                (
                    status, json.dumps(response or {}, ensure_ascii=False),
                    conversation_id, remind_at, now_iso(), event_id,
                ),
            )
        return self.get_proactive_event(event_id)

    def start_intervention(
        self, intervention_id: str, title: str, event_id: str | None = None
    ) -> dict[str, Any]:
        timestamp = now_iso()
        record = {
            "id": str(uuid4()), "event_id": event_id,
            "intervention_id": intervention_id, "title": title,
            "status": "started", "helpful": None, "feedback": None,
            "started_at": timestamp, "completed_at": None, "updated_at": timestamp,
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO intervention_session VALUES "
                "(:id,:event_id,:intervention_id,:title,:status,:helpful,:feedback,"
                ":started_at,:completed_at,:updated_at)",
                record,
            )
        return {**record, "helpful": None}

    def intervention_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM intervention_session ORDER BY started_at DESC LIMIT ?", (limit,)
            )]
        for row in rows:
            row["helpful"] = None if row["helpful"] is None else bool(row["helpful"])
        return rows

    def update_intervention_session(
        self,
        session_id: str,
        status: str,
        helpful: bool | None = None,
        feedback: str | None = None,
    ) -> dict[str, Any] | None:
        timestamp = now_iso()
        with self._connect() as db:
            db.execute(
                "UPDATE intervention_session SET status=?,helpful=?,feedback=?,"
                "completed_at=?,updated_at=? WHERE id=?",
                (
                    status, None if helpful is None else int(helpful), feedback,
                    timestamp if status in {"completed", "stopped"} else None,
                    timestamp, session_id,
                ),
            )
            row = db.execute(
                "SELECT * FROM intervention_session WHERE id=?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["helpful"] = None if result["helpful"] is None else bool(result["helpful"])
        return result

    @staticmethod
    def _decode_profile_fact(record: dict[str, Any]) -> dict[str, Any]:
        result = dict(record)
        result["value"] = json.loads(result.pop("value_json", "{}"))
        return result

    @staticmethod
    def _decode_proactive_event(record: dict[str, Any]) -> dict[str, Any]:
        result = dict(record)
        result["context"] = json.loads(result.pop("context_json", "{}"))
        result["response"] = json.loads(result.pop("response_json", "{}"))
        return result

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

    def dismiss_other_assistant_actions(
        self,
        message_id: str,
        chosen_action_id: str,
        kinds: tuple[str, ...] = ("device_control_allow", "device_control_deny"),
    ) -> None:
        placeholders = ",".join("?" for _ in kinds)
        with self._connect() as db:
            db.execute(
                "UPDATE assistant_action SET status='dismissed',updated_at=? "
                "WHERE message_id=? AND id<>? AND status='pending' "
                f"AND kind IN ({placeholders})",
                (now_iso(), message_id, chosen_action_id, *kinds),
            )

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
