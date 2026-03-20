import asyncio
import logging

from app.bot.services.discord_service import DiscordTrackingService
from app.bot.services.voice_service import VoicePlaybackService
from app.db.models import get_runtime_config, get_tracked_user_by_discord_id
from app.db.session_models import get_active_session

logger = logging.getLogger("voice")


class VoiceEventHandler:
    def __init__(self, target_voice_channel_id: int):
        self.target_voice_channel_id = target_voice_channel_id
        self.tracking_service = DiscordTrackingService()
        self.voice_playback = VoicePlaybackService()

        self.pending_end_tasks: dict[int, asyncio.Task] = {}
        self.pending_anchor_tasks: dict[int, asyncio.Task] = {}

    async def _maybe_play_join_sound(self, member, after):
        cfg = get_runtime_config()
        if not cfg["voice_join_sounds_enabled"]:
            return

        tracked_user = get_tracked_user_by_discord_id(member.id)
        if not tracked_user:
            return

        if not tracked_user["join_sound_enabled"]:
            return

        if not tracked_user["join_sound_path"]:
            return

        try:
            await self.voice_playback.play_join_sound(
                channel=after.channel,
                sound_path=tracked_user["join_sound_path"],
            )
        except Exception:
            logger.exception(f"Failed to play join sound for {member.display_name}")

    def _cancel_pending_end(self, discord_user_id: int):
        task = self.pending_end_tasks.pop(discord_user_id, None)
        if task and not task.done():
            task.cancel()

    def _cancel_pending_anchor(self, session_id: int):
        task = self.pending_anchor_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    async def _delayed_anchor(self, session_id: int, pubg_handle: str, delay_seconds: int):
        try:
            logger.info(
                f"Waiting {delay_seconds}s before checking first match "
                f"for session {session_id} ({pubg_handle})"
            )
            await asyncio.sleep(delay_seconds)

            session = get_active_session_by_session_id(session_id)
            if not session:
                logger.info(f"Session {session_id} ended before first-match check")
                return

            if session["first_match_at"]:
                logger.info(f"Session {session_id} already has first match anchored")
                return

            self.tracking_service.enqueue_session_anchor_if_needed(session_id)
            logger.info(f"Queued first-match check for session {session_id} ({pubg_handle})")

        except asyncio.CancelledError:
            logger.info(f"Cancelled pending first-match check for session {session_id}")
            raise
        finally:
            self.pending_anchor_tasks.pop(session_id, None)

    async def _delayed_end(self, discord_user_id: int, discord_name: str, delay_seconds: int):
        try:
            logger.info(
                f"{discord_name} left target VC. Waiting {delay_seconds}s before ending session."
            )
            await asyncio.sleep(delay_seconds)

            still_active = get_active_session(discord_user_id)
            if not still_active:
                logger.info(f"No active session remained for {discord_name}")
                return

            ended = self.tracking_service.end_session_if_needed(discord_user_id)

            if ended:
                logger.info(
                    f"Ended tracking session for {discord_name} "
                    f"(session_id={ended['id']}, pubg={ended['pubg_handle']})"
                )
            else:
                logger.info(f"No active session to end for {discord_name}")

        except asyncio.CancelledError:
            logger.info(f"{discord_name} rejoined within grace period, continuing same session")
            raise
        finally:
            self.pending_end_tasks.pop(discord_user_id, None)

    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        cfg = get_runtime_config()
        session_end_grace_seconds = int(cfg["session_end_grace_seconds"])
        session_anchor_delay_seconds = int(cfg["session_anchor_delay_seconds"])

        joined_target = (
            after.channel is not None
            and after.channel.id == self.target_voice_channel_id
            and (before.channel is None or before.channel.id != self.target_voice_channel_id)
        )

        if joined_target:
            self._cancel_pending_end(member.id)

            started = self.tracking_service.begin_session_if_needed(
                discord_user_id=member.id,
                discord_name=member.display_name,
                voice_channel_id=after.channel.id,
            )

            if started:
                if started.get("reused_existing"):
                    logger.info(
                        f"Continuing existing tracking session for {member.display_name} "
                        f"(session_id={started['session_id']}, pubg={started['pubg_handle']})"
                    )
                else:
                    logger.info(
                        f"Started tracking session for {member.display_name} "
                        f"(session_id={started['session_id']}, pubg={started['pubg_handle']})"
                    )
                    anchor_task = asyncio.create_task(
                        self._delayed_anchor(
                            session_id=started["session_id"],
                            pubg_handle=started["pubg_handle"],
                            delay_seconds=session_anchor_delay_seconds,
                        )
                    )
                    self.pending_anchor_tasks[started["session_id"]] = anchor_task
            else:
                logger.info(f"No tracking started for {member.display_name}")

            await self._maybe_play_join_sound(member, after)
            return

        left_target = (
            before.channel is not None
            and before.channel.id == self.target_voice_channel_id
            and (after.channel is None or after.channel.id != self.target_voice_channel_id)
        )

        if left_target:
            self._cancel_pending_end(member.id)

            end_task = asyncio.create_task(
                self._delayed_end(
                    discord_user_id=member.id,
                    discord_name=member.display_name,
                    delay_seconds=session_end_grace_seconds,
                )
            )
            self.pending_end_tasks[member.id] = end_task

            try:
                await self.voice_playback.disconnect_if_alone()
            except Exception:
                logger.exception("Failed during voice disconnect cleanup")


def get_active_session_by_session_id(session_id: int):
    from app.db.session_models import get_session

    session = get_session(session_id)
    if not session:
        return None

    if session["status"] != "active":
        return None

    return session