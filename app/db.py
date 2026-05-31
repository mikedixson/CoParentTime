from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS planning_runs (
                run_id TEXT PRIMARY KEY,
                planning_period TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                input_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS run_inputs (
                run_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES planning_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS run_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                rank_idx INTEGER,
                candidate_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES planning_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS run_results (
                run_id TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES planning_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS run_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                audit_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES planning_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS clarification_threads (
                run_id TEXT PRIMARY KEY,
                clarifications_json TEXT NOT NULL,
                responses_json TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES planning_runs(run_id)
            );
            """
        )


def save_run_header(run_id: str, planning_period: str, status: str, input_hash: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO planning_runs (run_id, planning_period, created_at, status, input_hash)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, planning_period, datetime.now(timezone.utc).isoformat(), status, input_hash),
        )


def save_run_input(run_id: str, payload: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO run_inputs (run_id, payload_json) VALUES (?, ?)",
            (run_id, json.dumps(payload, default=str, sort_keys=True)),
        )


def save_candidates(run_id: str, candidates: list[dict]) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM run_candidates WHERE run_id = ?", (run_id,))
        for idx, candidate in enumerate(candidates):
            conn.execute(
                """
                INSERT INTO run_candidates (run_id, plan_id, rank_idx, candidate_json)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, candidate.get("plan_id"), idx + 1, json.dumps(candidate, default=str)),
            )


def save_result(run_id: str, result: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO run_results (run_id, result_json) VALUES (?, ?)",
            (run_id, json.dumps(result, default=str)),
        )


def save_audit(run_id: str, audit_type: str, payload: dict | list) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO run_audits (run_id, audit_type, payload_json) VALUES (?, ?, ?)",
            (run_id, audit_type, json.dumps(payload, default=str)),
        )


def save_clarifications(run_id: str, clarifications: list[dict], responses: dict, status: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO clarification_threads
            (run_id, clarifications_json, responses_json, status)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, json.dumps(clarifications), json.dumps(responses), status),
        )


def get_run_result(run_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT result_json FROM run_results WHERE run_id = ?", (run_id,)).fetchone()
    if not row:
        return None
    return json.loads(row["result_json"])
