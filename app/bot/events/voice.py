import logging

from app.bot.services.discord_service import DiscordTrackingService
from app.bot.services.voice_service import VoicePlaybackService
from app.db.models import get_runtime_config, get_tracked_user_by_discord_id

logger = logging.getLogger("voice")


class VoiceEventHandler:
    def __init__(self, target_voice_channel_id: int):
        self.target_voice_channel_id = target_voice_channel_id
        self.tracking_service = DiscordTrackingService()
        self.voice_playback = VoicePlaybackService()

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

    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        joined_target = (
            after.channel is not None
            and after.channel.id == self.target_voice_channel_id
            and (before.channel is None or before.channel.id != self.target_voice_channel_id)
        )

        if joined_target:
            started = self.tracking_service.begin_session_if_needed(
                discord_user_id=member.id,
                discord_name=member.display_name,
                voice_channel_id=after.channel.id,
            )

            if started:
                logger.info(
                    f"Started tracking session for {member.display_name} "
                    f"(session_id={started['session_id']}, pubg={started['pubg_handle']})"
                )
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
            ended = self.tracking_service.end_session_if_needed(member.id)

            if ended:
                logger.info(
                    f"Ended tracking session for {member.display_name} "
                    f"(session_id={ended['id']}, pubg={ended['pubg_handle']})"
                )
            else:
                logger.info(f"No active session to end for {member.display_name}")

            try:
                await self.voice_playback.disconnect_if_alone()
            except Exception:
                logger.exception("Failed during voice disconnect cleanup")