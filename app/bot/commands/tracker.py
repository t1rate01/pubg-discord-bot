import asyncio
import discord
from discord import app_commands

from app.db.models import (
    get_tracked_user_by_discord_id,
    upsert_tracked_user_by_discord_id,
    set_tracking_enabled_by_discord_id,
)
from app.db.runtime_models import (
    enqueue_job,
    get_job,
    count_queued_jobs,
    count_active_high_priority_jobs,
)
from app.db.models import get_runtime_config


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return float(numerator)
    return numerator / denominator


def calc_kd(kills: int, losses: int) -> float:
    return safe_div(kills, losses)


def calc_kda(kills: int, assists: int, losses: int) -> float:
    return safe_div(kills + assists, losses)


def build_stats_embed(result: dict) -> discord.Embed:
    parsed = result["parsed"]

    solo_fpp = parsed["solo_fpp"]
    duo_fpp = parsed["duo_fpp"]
    squad_fpp = parsed["squad_fpp"]
    ranked_duo = parsed["ranked_duo"]
    ranked_squad = parsed["ranked_squad"]

    embed = discord.Embed(
        title=f"PUBG Stats — {parsed['player_name']}",
    )

    embed.add_field(
        name="Overall (Normal FPP)",
        value=(
            f"Games: **{parsed['normal_rounds']}**\n"
            f"KD: **{calc_kd(parsed['normal_kills'], parsed['normal_losses']):.2f}**\n"
            f"KDA: **{calc_kda(parsed['normal_kills'], parsed['normal_assists'], parsed['normal_losses']):.2f}**\n"
            f"Kills: **{parsed['normal_kills']}**\n"
            f"Avg Dmg: **{safe_div(parsed['normal_damage'], parsed['normal_rounds']) if parsed['normal_rounds'] else 0:.1f}**"
        ),
        inline=False,
    )

    embed.add_field(
        name="Overall (Ranked FPP)",
        value=(
            f"Games: **{parsed['ranked_rounds']}**\n"
            f"KD: **{calc_kd(parsed['ranked_kills'], parsed['ranked_deaths']):.2f}**\n"
            f"KDA: **{calc_kda(parsed['ranked_kills'], parsed['ranked_assists'], parsed['ranked_deaths']):.2f}**\n"
            f"Kills: **{parsed['ranked_kills']}**\n"
            f"Avg Dmg: **{safe_div(parsed['ranked_damage'], parsed['ranked_rounds']) if parsed['ranked_rounds'] else 0:.1f}**"
        ),
        inline=False,
    )

    embed.add_field(
        name="Solo FPP",
        value=f"Games: {solo_fpp['rounds']}\nKD: {solo_fpp['kd']:.2f}\nKDA: {solo_fpp['kda']:.2f}",
        inline=True,
    )
    embed.add_field(
        name="Duo FPP",
        value=f"Games: {duo_fpp['rounds']}\nKD: {duo_fpp['kd']:.2f}\nKDA: {duo_fpp['kda']:.2f}",
        inline=True,
    )
    embed.add_field(
        name="Squad FPP",
        value=f"Games: {squad_fpp['rounds']}\nKD: {squad_fpp['kd']:.2f}\nKDA: {squad_fpp['kda']:.2f}",
        inline=True,
    )

    ranked_tier = ranked_squad["current_tier"] or ranked_duo["current_tier"]
    ranked_best_tier = ranked_squad["best_tier"] or ranked_duo["best_tier"]

    embed.add_field(
        name="Ranked Summary",
        value=(
            f"Current: **{ranked_tier.get('tier', 'N/A')} {ranked_tier.get('subTier', '')}**\n"
            f"Best: **{ranked_best_tier.get('tier', 'N/A')} {ranked_best_tier.get('subTier', '')}**\n"
            f"RP: **{max(ranked_duo['current_rank_point'], ranked_squad['current_rank_point'])}**"
        ),
        inline=False,
    )

    return embed


class TrackerCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="tracker", description="PUBG tracking commands")

    @app_commands.command(name="mystatus", description="Show your current tracking status")
    async def mystatus(self, interaction: discord.Interaction):
        user = interaction.user
        existing = get_tracked_user_by_discord_id(user.id)

        if not existing:
            await interaction.response.send_message(
                "You are not registered yet. Use `/tracker trackme` first.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                f"**Discord:** {existing['discord_name']}\n"
                f"**PUBG handle:** {existing['pubg_handle'] or 'Not set'}\n"
                f"**Tracking enabled:** {'Yes' if existing['tracking_enabled'] else 'No'}\n"
                f"**History saving:** {'Yes' if existing['history_enabled'] else 'No'}"
            ),
            ephemeral=True,
        )

    @app_commands.command(name="trackme", description="Enable tracking for yourself with your PUBG handle")
    async def trackme(self, interaction: discord.Interaction, pubg_handle: str):
        user = interaction.user

        upsert_tracked_user_by_discord_id(
            discord_user_id=user.id,
            discord_name=user.display_name,
            pubg_handle=pubg_handle.strip(),
            tracking_enabled=True,
        )

        await interaction.response.send_message(
            f"Tracking enabled for **{user.display_name}** with PUBG handle **{pubg_handle}**.",
            ephemeral=True,
        )

    @app_commands.command(name="untrackme", description="Disable tracking for yourself")
    async def untrackme(self, interaction: discord.Interaction):
        user = interaction.user
        existing = get_tracked_user_by_discord_id(user.id)

        if not existing:
            await interaction.response.send_message(
                "You are not currently registered for tracking.",
                ephemeral=True,
            )
            return

        set_tracking_enabled_by_discord_id(user.id, False)

        await interaction.response.send_message(
            "Tracking disabled for your account.",
            ephemeral=True,
        )

    @app_commands.command(name="stats", description="Check PUBG stats")
    async def stats(self, interaction: discord.Interaction, pubg_handle: str):
        cfg = get_runtime_config()
        poll_seconds = float(cfg["pubg_job_result_poll_seconds"])
        max_wait_seconds = float(cfg["pubg_job_result_max_wait_seconds"])

        queue_size = count_queued_jobs()
        high_priority_busy = count_active_high_priority_jobs()

        job_id = enqueue_job(
            job_type="stats_lookup",
            discord_user_id=interaction.user.id,
            pubg_handle=pubg_handle.strip(),
            priority=10,
            payload={"pubg_handle": pubg_handle.strip()},
        )

        await interaction.response.defer(thinking=True)

        if high_priority_busy > 0:
            await interaction.followup.send(
                "⏳ Session reports are currently being built. Your stats request has been queued.",
                ephemeral=True,
            )
        elif queue_size > 0:
            await interaction.followup.send(
                f"⏳ Queue busy. Your position: {queue_size + 1}",
                ephemeral=True,
            )

        max_checks = max(1, int(max_wait_seconds / poll_seconds))

        for _ in range(max_checks):
            await asyncio.sleep(poll_seconds)
            job = get_job(job_id)

            if not job:
                continue

            if job["status"] == "done":
                embed = build_stats_embed(job["result_json"])
                await interaction.followup.send(embed=embed)
                return

            if job["status"] == "failed":
                await interaction.followup.send(
                    f"❌ Failed: {job['error_text']}"
                )
                return

        await interaction.followup.send("⚠️ Timeout, try again.")