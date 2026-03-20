from app.db.models import get_tracked_user_by_discord_id
from app.db.session_models import (
    get_active_session,
    start_tracking_session,
    end_tracking_session,
    get_session,
)
from app.db.runtime_models import enqueue_job


class DiscordTrackingService:
    def begin_session_if_needed(
        self,
        discord_user_id: int,
        discord_name: str,
        voice_channel_id: int,
    ) -> dict | None:
        user = get_tracked_user_by_discord_id(discord_user_id)
        if not user:
            return None

        if not user["tracking_enabled"]:
            return None

        if not user["pubg_handle"]:
            return None

        existing = get_active_session(discord_user_id)
        if existing:
            return {
                "session_id": existing["id"],
                "discord_name": existing["discord_name"],
                "pubg_handle": existing["pubg_handle"],
                "history_enabled": bool(user["history_enabled"]),
                "reused_existing": True,
            }

        session_id = start_tracking_session(
            discord_user_id=discord_user_id,
            discord_name=discord_name,
            pubg_handle=user["pubg_handle"],
            voice_channel_id=voice_channel_id,
        )

        created_session = get_session(session_id)

        return {
            "session_id": session_id,
            "discord_name": discord_name,
            "pubg_handle": user["pubg_handle"],
            "history_enabled": bool(user["history_enabled"]),
            "started_at": created_session["started_at"] if created_session else None,
            "reused_existing": False,
        }

    def enqueue_session_anchor_if_needed(self, session_id: int) -> None:
        session = get_session(session_id)
        if not session:
            return

        if session["first_match_at"]:
            return

        enqueue_job(
            job_type="session_anchor",
            discord_user_id=int(session["discord_user_id"]),
            pubg_handle=session["pubg_handle"],
            session_id=session["id"],
            priority=90,
            payload={
                "session_id": session["id"],
                "discord_name": session["discord_name"],
                "pubg_handle": session["pubg_handle"],
                "started_at": session["started_at"],
            },
        )

    def end_session_if_needed(self, discord_user_id: int) -> dict | None:
        existing = get_active_session(discord_user_id)
        if not existing:
            return None

        end_tracking_session(existing["id"])
        ended_session = get_session(existing["id"])

        if not ended_session:
            return None

        enqueue_job(
            job_type="session_finalize",
            discord_user_id=int(ended_session["discord_user_id"]),
            pubg_handle=ended_session["pubg_handle"],
            session_id=ended_session["id"],
            priority=100,
            payload={
                "session_id": ended_session["id"],
                "discord_name": ended_session["discord_name"],
                "pubg_handle": ended_session["pubg_handle"],
                "started_at": ended_session["started_at"],
                "first_match_at": ended_session["first_match_at"],
                "ended_at": ended_session["ended_at"],
            },
        )

        return ended_session