import json
from typing import Optional

from app.db.sqlite import get_connection


def _decode_job(row) -> Optional[dict]:
    if not row:
        return None

    job = dict(row)

    if job.get("payload_json"):
        try:
            job["payload_json"] = json.loads(job["payload_json"])
        except json.JSONDecodeError:
            pass

    if job.get("result_json"):
        try:
            job["result_json"] = json.loads(job["result_json"])
        except json.JSONDecodeError:
            pass

    return job


def enqueue_job(
    job_type: str,
    discord_user_id: int | None = None,
    pubg_handle: str | None = None,
    priority: int = 0,
    session_id: int | None = None,
    payload: dict | None = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO pubg_request_jobs (
                job_type,
                discord_user_id,
                pubg_handle,
                session_id,
                payload_json,
                priority
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_type,
                str(discord_user_id) if discord_user_id is not None else None,
                pubg_handle,
                session_id,
                json.dumps(payload) if payload else None,
                priority,
            ),
        )
        return cur.lastrowid


def get_next_job() -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM pubg_request_jobs
            WHERE status = 'queued'
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
            """
        ).fetchone()

        return _decode_job(row)


def mark_job_processing(job_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE pubg_request_jobs
            SET status = 'processing',
                started_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (job_id,),
        )


def mark_job_done(job_id: int, result: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE pubg_request_jobs
            SET status = 'done',
                result_json = ?,
                finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (json.dumps(result), job_id),
        )


def mark_job_failed(job_id: int, error: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE pubg_request_jobs
            SET status = 'failed',
                error_text = ?,
                finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (error, job_id),
        )


def get_job(job_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM pubg_request_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

        return _decode_job(row)


def count_queued_jobs() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM pubg_request_jobs WHERE status = 'queued'"
        ).fetchone()
        return row["count"]


def count_active_high_priority_jobs(min_priority: int = 100) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM pubg_request_jobs
            WHERE status IN ('queued', 'processing')
              AND priority >= ?
            """,
            (min_priority,),
        ).fetchone()
        return row["count"]