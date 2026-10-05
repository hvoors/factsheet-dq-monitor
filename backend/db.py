import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "dq_monitor.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isin TEXT NOT NULL,
            category TEXT NOT NULL,
            fund_name TEXT NOT NULL,
            klasse_name TEXT NOT NULL,
            template TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            report_period TEXT,
            pdf_path TEXT NOT NULL,
            page_count INTEGER,
            page_image_counts TEXT,
            source TEXT NOT NULL DEFAULT 'fetch',
            status TEXT NOT NULL,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            severity TEXT NOT NULL,
            code TEXT NOT NULL,
            message TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_runs_isin ON runs(isin);
        CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id);
        """
    )
    conn.commit()
    conn.close()


def insert_run(conn, run: dict) -> int:
    cur = conn.execute(
        """
        INSERT INTO runs (isin, category, fund_name, klasse_name, template, fetched_at,
                           report_period, pdf_path, page_count, page_image_counts, source, status, error_message)
        VALUES (:isin, :category, :fund_name, :klasse_name, :template, :fetched_at,
                :report_period, :pdf_path, :page_count, :page_image_counts, :source, :status, :error_message)
        """,
        run,
    )
    conn.commit()
    return cur.lastrowid


def insert_findings(conn, run_id: int, findings: list[dict]):
    for f in findings:
        conn.execute(
            "INSERT INTO findings (run_id, severity, code, message) VALUES (?, ?, ?, ?)",
            (run_id, f["severity"], f["code"], f["message"]),
        )
    conn.commit()


def get_previous_run(conn, isin: str, before_run_id: int | None = None):
    if before_run_id is None:
        row = conn.execute(
            "SELECT * FROM runs WHERE isin = ? AND status = 'ok' ORDER BY id DESC LIMIT 1",
            (isin,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM runs WHERE isin = ? AND status = 'ok' AND id < ? ORDER BY id DESC LIMIT 1",
            (isin, before_run_id),
        ).fetchone()
    return row


def get_latest_runs(conn):
    rows = conn.execute(
        """
        SELECT r.* FROM runs r
        INNER JOIN (
            SELECT isin, MAX(id) AS max_id FROM runs GROUP BY isin
        ) latest ON r.isin = latest.isin AND r.id = latest.max_id
        """
    ).fetchall()
    return rows


def get_findings_for_run(conn, run_id: int):
    return conn.execute("SELECT * FROM findings WHERE run_id = ?", (run_id,)).fetchall()


def get_history(conn, isin: str, limit: int = 12):
    return conn.execute(
        "SELECT * FROM runs WHERE isin = ? ORDER BY id DESC LIMIT ?", (isin, limit)
    ).fetchall()
