import asyncio
import logging
from pathlib import Path

import discord

logger = logging.getLogger("voice_service")


class VoicePlaybackService:
    def __init__(self):
        self.voice_client: discord.VoiceClient | None = None
        self._lock = asyncio.Lock()

    async def ensure_connected(self, channel: discord.VoiceChannel) -> discord.VoiceClient:
        if self.voice_client and self.voice_client.is_connected():
            if self.voice_client.channel.id != channel.id:
                await self.voice_client.move_to(channel)
            return self.voice_client

        self.voice_client = await channel.connect()
        return self.voice_client

    async def play_join_sound(self, channel: discord.VoiceChannel, sound_path: str) -> None:
        async with self._lock:
            path = Path(sound_path)

            if not path.exists():
                logger.warning(f"Join sound file does not exist: {sound_path}")
                return

            voice_client = await self.ensure_connected(channel)

            if voice_client.is_playing():
                logger.info("Voice client already playing, skipping join sound")
                return

            logger.info(f"Playing join sound: {sound_path}")

            source = discord.FFmpegPCMAudio(str(path))
            voice_client.play(source)

    async def disconnect_if_alone(self) -> None:
        if not self.voice_client or not self.voice_client.is_connected():
            return

        channel = self.voice_client.channel
        human_count = sum(1 for m in channel.members if not m.bot)

        if human_count == 0:
            logger.info("No human users left in voice channel, disconnecting bot")
            await self.voice_client.disconnect()
            self.voice_client = None