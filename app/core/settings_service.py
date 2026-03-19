from app.db.models import (
    app_is_initialized,
    create_tracked_user,
    get_runtime_config,
    mark_app_initialized,
    runtime_config_complete,
    save_runtime_config,
)


SAFE_DEFAULTS = {
    "tracked_team_name": "My Stack",
    "admin_discord_ids": [],
    "voice_join_sounds_enabled": False,
    "pubg_job_worker_idle_poll_seconds": "10.0",
    "pubg_job_result_poll_seconds": "1.5",
    "pubg_job_result_max_wait_seconds": "30",
    "pubg_rate_limit_max_requests": "10",
    "pubg_rate_limit_window_seconds": "60",
}


def initialize_runtime_config(
    discord_bot_token: str,
    pubg_api_key: str,
    discord_guild_id: str,
    discord_target_voice_channel_id: str,
    discord_target_text_channel_id: str,
    tracked_team_name: str,
    admin_discord_ids: list[str] | None = None,
) -> None:
    payload = dict(SAFE_DEFAULTS)
    payload.update(
        {
            "discord_bot_token": discord_bot_token.strip(),
            "pubg_api_key": pubg_api_key.strip(),
            "discord_guild_id": discord_guild_id.strip(),
            "discord_target_voice_channel_id": discord_target_voice_channel_id.strip(),
            "discord_target_text_channel_id": discord_target_text_channel_id.strip(),
            "tracked_team_name": tracked_team_name.strip() or "My Stack",
            "admin_discord_ids": admin_discord_ids or [],
        }
    )

    save_runtime_config(payload)
    mark_app_initialized()


def system_state() -> dict:
    return {
        "app_initialized": app_is_initialized(),
        "runtime_config_complete": runtime_config_complete(),
        "runtime_config": get_runtime_config(),
    }