from typing import Optional

from app.db.sqlite import get_connection


def get_active_session(discord_user_id: int | str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM tracking_sessions
            WHERE discord_user_id = ?
              AND status = 'active'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (str(discord_user_id),),
        ).fetchone()
        return dict(row) if row else None


def start_tracking_session(
    discord_user_id: int,
    discord_name: str,
    pubg_handle: str,
    voice_channel_id: int,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO tracking_sessions (
                discord_user_id,
                discord_name,
                pubg_handle,
                voice_channel_id,
                status
            )
            VALUES (?, ?, ?, ?, 'active')
            """,
            (
                str(discord_user_id),
                discord_name,
                pubg_handle,
                str(voice_channel_id),
            ),
        )
        return cur.lastrowid


def set_first_match_at(session_id: int, first_match_at: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE tracking_sessions
            SET first_match_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (first_match_at, session_id),
        )


def end_tracking_session(session_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE tracking_sessions
            SET ended_at = CURRENT_TIMESTAMP,
                status = 'completed',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (session_id,),
        )


def get_session(session_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM tracking_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None