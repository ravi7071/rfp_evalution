from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_DB_PATH = Path("rfp_evaluation.db")


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Create a SQLite connection with row access by column name."""
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Create all Phase 1 tables if they do not exist."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_criteria (
                criterion_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                weight REAL NOT NULL CHECK (weight >= 0 AND weight <= 1),
                max_score INTEGER NOT NULL CHECK (max_score > 0),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rfp_runs (
                rfp_run_id TEXT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL,
                status TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS supplier_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfp_run_id TEXT NOT NULL,
                supplier_name TEXT NOT NULL,
                submission_date DATE NOT NULL,
                experience_rating INTEGER NOT NULL,
                absolute_score REAL,
                ppi REAL,
                final_rank INTEGER,
                result_json TEXT,
                FOREIGN KEY (rfp_run_id) REFERENCES rfp_runs (rfp_run_id)
            )
            """
        )


def seed_evaluation_criteria(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Insert default active criteria if they are not already present."""
    sample_criteria: list[tuple[str, str, float, int, int]] = [
        (
            "Technical",
            "Quality of technical architecture, feasibility, and scalability.",
            0.30,
            10,
            1,
        ),
        (
            "Implementation",
            "Clarity and strength of implementation timeline, plan, and staffing.",
            0.25,
            10,
            1,
        ),
        (
            "Commercial",
            "Cost competitiveness and commercial value for money.",
            0.20,
            10,
            1,
        ),
        (
            "Security",
            "Security posture, compliance, and risk mitigation quality.",
            0.15,
            10,
            1,
        ),
        (
            "Support",
            "Post-implementation support, SLAs, and operational responsiveness.",
            0.10,
            10,
            1,
        ),
    ]

    total_weight = sum(weight for _, _, weight, _, is_active in sample_criteria if is_active)
    if abs(total_weight - 1.0) > 1e-9:
        raise ValueError(f"Active criteria weights must sum to 1.0, found {total_weight}")

    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.executemany(
            """
            INSERT OR IGNORE INTO evaluation_criteria (name, description, weight, max_score, is_active)
            VALUES (?, ?, ?, ?, ?)
            """,
            sample_criteria,
        )


def get_active_criteria(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """Return all active criteria ordered by criterion id."""
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        rows = cursor.execute(
            """
            SELECT criterion_id, name, description, weight, max_score, is_active
            FROM evaluation_criteria
            WHERE is_active = 1
            ORDER BY criterion_id ASC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def create_rfp_run(db_path: str | Path = DEFAULT_DB_PATH, status: str = "initialized") -> str:
    """Create a new RFP run entry and return its run id."""
    rfp_run_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO rfp_runs (rfp_run_id, created_at, status)
            VALUES (?, ?, ?)
            """,
            (rfp_run_id, created_at, status),
        )

    return rfp_run_id


def update_rfp_run_status(
    rfp_run_id: str,
    status: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE rfp_runs
            SET status = ?
            WHERE rfp_run_id = ?
            """,
            (status, rfp_run_id),
        )


def delete_supplier_results_for_run(rfp_run_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            DELETE FROM supplier_results
            WHERE rfp_run_id = ?
            """,
            (rfp_run_id,),
        )


def save_supplier_result(
    rfp_run_id: str,
    supplier_name: str,
    submission_date: str,
    experience_rating: int,
    absolute_score: float,
    ppi: float,
    final_rank: int,
    result_payload: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    result_json = json.dumps(result_payload, ensure_ascii=False)
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO supplier_results (
                rfp_run_id,
                supplier_name,
                submission_date,
                experience_rating,
                absolute_score,
                ppi,
                final_rank,
                result_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rfp_run_id,
                supplier_name,
                submission_date,
                experience_rating,
                absolute_score,
                ppi,
                final_rank,
                result_json,
            ),
        )
        return int(cursor.lastrowid)


def list_rfp_runs(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        rows = cursor.execute(
            """
            SELECT
                r.rfp_run_id,
                r.created_at,
                r.status,
                COUNT(s.id) AS supplier_count
            FROM rfp_runs r
            LEFT JOIN supplier_results s ON s.rfp_run_id = r.rfp_run_id
            GROUP BY r.rfp_run_id, r.created_at, r.status
            ORDER BY r.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_supplier_results_for_run(
    rfp_run_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    with get_connection(db_path) as connection:
        cursor = connection.cursor()
        rows = cursor.execute(
            """
            SELECT
                id,
                rfp_run_id,
                supplier_name,
                submission_date,
                experience_rating,
                absolute_score,
                ppi,
                final_rank,
                result_json
            FROM supplier_results
            WHERE rfp_run_id = ?
            ORDER BY final_rank ASC, supplier_name ASC
            """,
            (rfp_run_id,),
        ).fetchall()
    return [dict(row) for row in rows]

