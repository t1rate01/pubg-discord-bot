import logging
import discord

from app.db.models import get_runtime_config
from app.bot.events.voice import VoiceEventHandler
from app.bot.commands.tracker import TrackerCommands

logger = logging.getLogger("discord_bot")


class PubgDiscordBot(discord.Client):
    def __init__(self, target_voice_channel_id: int, guild_id: int):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.voice_states = True

        super().__init__(intents=intents)

        self.guild_id = guild_id
        self.tree = discord.app_commands.CommandTree(self)
        self.voice_handler = VoiceEventHandler(target_voice_channel_id)

    async def setup_hook(self):
        guild = discord.Object(id=self.guild_id)
        self.tree.clear_commands(guild=guild)
        self.tree.add_command(TrackerCommands(), guild=guild)
        synced = await self.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} guild application commands")

    async def on_ready(self):
        logger.info(f"Discord bot connected as {self.user}")

    async def on_voice_state_update(self, member, before, after):
        await self.voice_handler.on_voice_state_update(member, before, after)


def build_bot_from_db() -> tuple[PubgDiscordBot, str]:
    cfg = get_runtime_config()

    token = cfg["discord_bot_token"]
    guild_id = int(cfg["discord_guild_id"])
    target_voice_channel_id = int(cfg["discord_target_voice_channel_id"])

    client = PubgDiscordBot(
        target_voice_channel_id=target_voice_channel_id,
        guild_id=guild_id,
    )

    return client, token