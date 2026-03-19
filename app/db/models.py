import json
from typing import Optional

from app.db.sqlite import get_connection


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def get_bool_setting(key: str, default: bool = False) -> bool:
    value = get_setting(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def set_bool_setting(key: str, value: bool) -> None:
    set_setting(key, "true" if value else "false")


def get_json_setting(key: str, default=None):
    value = get_setting(key)
    if value is None:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def set_json_setting(key: str, value) -> None:
    set_setting(key, json.dumps(value))


def app_is_initialized() -> bool:
    return get_bool_setting("app_initialized", False)


def mark_app_initialized() -> None:
    set_bool_setting("app_initialized", True)


def runtime_config_complete() -> bool:
    required = [
        "discord_bot_token",
        "pubg_api_key",
        "discord_guild_id",
        "discord_target_voice_channel_id",
        "discord_target_text_channel_id",
    ]
    return all(get_setting(key) for key in required)


def get_runtime_config() -> dict:
    return {
        "discord_bot_token": get_setting("discord_bot_token", ""),
        "pubg_api_key": get_setting("pubg_api_key", ""),
        "discord_guild_id": get_setting("discord_guild_id", ""),
        "discord_target_voice_channel_id": get_setting("discord_target_voice_channel_id", ""),
        "discord_target_text_channel_id": get_setting("discord_target_text_channel_id", ""),
        "tracked_team_name": get_setting("tracked_team_name", "My Stack"),
        "admin_discord_ids": get_json_setting("admin_discord_ids", []),
        "voice_join_sounds_enabled": get_bool_setting("voice_join_sounds_enabled", False),
        "pubg_job_worker_idle_poll_seconds": float(get_setting("pubg_job_worker_idle_poll_seconds", "10.0")),
        "pubg_job_result_poll_seconds": float(get_setting("pubg_job_result_poll_seconds", "1.5")),
        "pubg_job_result_max_wait_seconds": float(get_setting("pubg_job_result_max_wait_seconds", "30")),
        "pubg_rate_limit_max_requests": int(get_setting("pubg_rate_limit_max_requests", "10")),
        "pubg_rate_limit_window_seconds": int(get_setting("pubg_rate_limit_window_seconds", "60")),
    }


def save_runtime_config(data: dict) -> None:
    for key, value in data.items():
        if isinstance(value, bool):
            set_bool_setting(key, value)
        elif isinstance(value, (list, dict)):
            set_json_setting(key, value)
        else:
            set_setting(key, str(value))


def list_tracked_users() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM tracked_users
            ORDER BY history_enabled DESC, discord_name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_tracked_user_by_id(user_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tracked_users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_tracked_user_by_discord_id(discord_user_id: int | str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tracked_users WHERE discord_user_id = ?",
            (str(discord_user_id),),
        ).fetchone()
        return dict(row) if row else None


def create_tracked_user(
    discord_user_id: str,
    discord_name: str,
    pubg_handle: Optional[str],
    tracking_enabled: bool,
    history_enabled: bool,
    join_sound_enabled: bool = False,
    join_sound_path: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tracked_users (
                discord_user_id,
                discord_name,
                pubg_handle,
                tracking_enabled,
                history_enabled,
                join_sound_enabled,
                join_sound_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                discord_user_id,
                discord_name,
                pubg_handle,
                int(tracking_enabled),
                int(history_enabled),
                int(join_sound_enabled),
                join_sound_path,
            ),
        )


def update_tracked_user(
    user_id: int,
    discord_user_id: str,
    discord_name: str,
    pubg_handle: Optional[str],
    tracking_enabled: bool,
    history_enabled: bool,
    join_sound_enabled: bool,
    join_sound_path: Optional[str],
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE tracked_users
            SET discord_user_id = ?,
                discord_name = ?,
                pubg_handle = ?,
                tracking_enabled = ?,
                history_enabled = ?,
                join_sound_enabled = ?,
                join_sound_path = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                discord_user_id,
                discord_name,
                pubg_handle,
                int(tracking_enabled),
                int(history_enabled),
                int(join_sound_enabled),
                join_sound_path,
                user_id,
            ),
        )


def delete_tracked_user(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM tracked_users WHERE id = ?", (user_id,))


def dashboard_counts() -> dict:
    with get_connection() as conn:
        tracked = conn.execute("SELECT COUNT(*) AS count FROM tracked_users").fetchone()["count"]
        history_enabled = conn.execute("SELECT COUNT(*) AS count FROM tracked_users WHERE history_enabled = 1").fetchone()["count"]
        tracking_enabled = conn.execute("SELECT COUNT(*) AS count FROM tracked_users WHERE tracking_enabled = 1").fetchone()["count"]
        queued_jobs = conn.execute("SELECT COUNT(*) AS count FROM pubg_request_jobs WHERE status = 'queued'").fetchone()["count"]
        processing_jobs = conn.execute("SELECT COUNT(*) AS count FROM pubg_request_jobs WHERE status = 'processing'").fetchone()["count"]
        reports = conn.execute("SELECT COUNT(*) AS count FROM session_reports").fetchone()["count"]

        return {
            "tracked": tracked,
            "history_enabled": history_enabled,
            "tracking_enabled": tracking_enabled,
            "queued_jobs": queued_jobs,
            "processing_jobs": processing_jobs,
            "reports": reports,
        }


def list_recent_reports(limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM session_reports
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    
def get_report_by_id(report_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM session_reports
            WHERE id = ?
            """,
            (report_id,),
        ).fetchone()
        return dict(row) if row else None


def list_report_matches(report_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM session_report_matches
            WHERE session_report_id = ?
            ORDER BY created_at ASC
            """,
            (report_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    
def get_service_control_state() -> dict:
    runtime_complete = runtime_config_complete()

    bot_enabled = get_bool_setting("bot_enabled", True)
    worker_enabled = get_bool_setting("worker_enabled", True)

    bot_generation = int(get_setting("bot_generation", "1"))
    worker_generation = int(get_setting("worker_generation", "1"))

    return {
        "runtime_config_complete": runtime_complete,
        "bot_enabled": bot_enabled,
        "worker_enabled": worker_enabled,
        "bot_generation": bot_generation,
        "worker_generation": worker_generation,
    }


def set_service_enabled(service_name: str, enabled: bool) -> None:
    if service_name not in {"bot", "worker"}:
        raise ValueError("service_name must be 'bot' or 'worker'")

    set_bool_setting(f"{service_name}_enabled", enabled)


def bump_service_generation(service_name: str) -> int:
    if service_name not in {"bot", "worker"}:
        raise ValueError("service_name must be 'bot' or 'worker'")

    current = int(get_setting(f"{service_name}_generation", "1"))
    new_value = current + 1
    set_setting(f"{service_name}_generation", str(new_value))
    return new_value


def request_service_restart(service_name: str) -> int:
    set_service_enabled(service_name, True)
    return bump_service_generation(service_name)


def request_all_services_restart() -> dict:
    set_service_enabled("bot", True)
    set_service_enabled("worker", True)

    return {
        "bot_generation": bump_service_generation("bot"),
        "worker_generation": bump_service_generation("worker"),
    }

def upsert_tracked_user_by_discord_id(
    discord_user_id: int,
    discord_name: str,
    pubg_handle: Optional[str] = None,
    tracking_enabled: bool = False,
) -> None:
    existing = get_tracked_user_by_discord_id(discord_user_id)

    if existing:
        update_tracked_user(
            user_id=existing["id"],
            discord_user_id=str(discord_user_id),
            discord_name=discord_name,
            pubg_handle=pubg_handle,
            tracking_enabled=tracking_enabled,
            history_enabled=bool(existing["history_enabled"]),
            join_sound_enabled=bool(existing["join_sound_enabled"]),
            join_sound_path=existing["join_sound_path"],
        )
    else:
        create_tracked_user(
            discord_user_id=str(discord_user_id),
            discord_name=discord_name,
            pubg_handle=pubg_handle,
            tracking_enabled=tracking_enabled,
            history_enabled=False,
            join_sound_enabled=False,
            join_sound_path=None,
        )


def set_tracking_enabled_by_discord_id(discord_user_id: int, enabled: bool) -> None:
    existing = get_tracked_user_by_discord_id(discord_user_id)
    if not existing:
        return

    update_tracked_user(
        user_id=existing["id"],
        discord_user_id=existing["discord_user_id"],
        discord_name=existing["discord_name"],
        pubg_handle=existing["pubg_handle"],
        tracking_enabled=enabled,
        history_enabled=bool(existing["history_enabled"]),
        join_sound_enabled=bool(existing["join_sound_enabled"]),
        join_sound_path=existing["join_sound_path"],
    )