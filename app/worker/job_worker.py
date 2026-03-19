import asyncio
import logging

import discord

from app.bot.services.pubg_service import PubgService
from app.db.models import (
    get_runtime_config,
    get_tracked_user_by_discord_id,
)
from app.db.runtime_models import (
    get_next_job,
    mark_job_processing,
    mark_job_done,
    mark_job_failed,
)
from app.db.session_models import (
    get_session,
    set_first_match_at,
)
from app.db.report_models import (
    save_session_report,
    save_session_report_matches,
)

logger = logging.getLogger("job_worker")


def build_session_report_embed(report: dict, discord_name: str | None = None) -> discord.Embed:
    title_name = discord_name or report["player"]

    total = report["total"]
    ranked = report["ranked"]
    normal = report["normal"]

    embed = discord.Embed(
        title=f"Session Report — {title_name}",
        description=f"PUBG handle: **{report['player']}**",
    )

    embed.add_field(
        name="Overall Session",
        value=(
            f"Games: **{total['rounds']}**\n"
            f"KD: **{total['kd']:.2f}**\n"
            f"KDA: **{total['kda']:.2f}**\n"
            f"Kills: **{total['kills']}**\n"
            f"Avg Dmg: **{total['avg_damage']:.1f}**\n"
            f"Wins: **{total['wins']}**\n"
            f"Top 10s: **{total['top10s']}**\n"
            f"Avg Place: **{total['avg_placement']:.1f}**"
        ),
        inline=False,
    )

    embed.add_field(
        name="Normal",
        value=(
            f"Games: {normal['rounds']}\n"
            f"KD: {normal['kd']:.2f}\n"
            f"KDA: {normal['kda']:.2f}\n"
            f"Avg Dmg: {normal['avg_damage']:.1f}"
        ),
        inline=True,
    )

    embed.add_field(
        name="Ranked",
        value=(
            f"Games: {ranked['rounds']}\n"
            f"KD: {ranked['kd']:.2f}\n"
            f"KDA: {ranked['kda']:.2f}\n"
            f"Avg Dmg: {ranked['avg_damage']:.1f}"
        ),
        inline=True,
    )

    embed.add_field(
        name="Tracked Window",
        value=(
            f"Start: `{report['started_at']}`\n"
            f"First match: `{report['first_match_at'] or '-'}\n"
            f"End: `{report['ended_at']}`"
        ),
        inline=False,
    )

    return embed


class JobWorker:
    def __init__(self, bot_client: discord.Client | None = None):
        self.bot_client = bot_client
        self.pubg_service = PubgService()

    async def _post_session_report(self, report: dict, job: dict):
        if not self.bot_client:
            logger.warning("Bot client not available, cannot post session report")
            return

        cfg = get_runtime_config()
        target_text_channel_id = cfg["discord_target_text_channel_id"]
        if not target_text_channel_id:
            logger.warning("Target text channel not configured")
            return

        channel = self.bot_client.get_channel(int(target_text_channel_id))
        if channel is None:
            logger.warning(f"Could not find target text channel {target_text_channel_id}")
            return

        payload = job.get("payload_json") or {}
        discord_name = payload.get("discord_name")

        embed = build_session_report_embed(report, discord_name=discord_name)
        await channel.send(embed=embed)

    def _save_report_if_history_enabled(self, report: dict, job: dict):
        discord_user_id = job.get("discord_user_id")
        if not discord_user_id:
            return

        tracked_user = get_tracked_user_by_discord_id(discord_user_id)
        if not tracked_user:
            return

        if not tracked_user["history_enabled"]:
            return

        payload = job.get("payload_json") or {}
        session_id = job.get("session_id") or payload.get("session_id")
        if not session_id:
            return

        report_id = save_session_report(
            session_id=int(session_id),
            discord_user_id=int(discord_user_id),
            discord_name=payload.get("discord_name"),
            pubg_handle=report["player"],
            report=report,
        )

        save_session_report_matches(report_id, report.get("games", []))
        logger.info(f"Saved report history for session {session_id}")

    async def _handle_session_anchor(self, job: dict):
        payload = job.get("payload_json") or {}

        session_id = int(payload["session_id"])
        pubg_handle = payload["pubg_handle"]
        started_at = payload["started_at"]

        first_match_at = self.pubg_service.find_first_session_match_time(
            pubg_handle=pubg_handle,
            started_at=started_at,
        )

        if first_match_at:
            set_first_match_at(session_id, first_match_at)
            logger.info(f"Anchored first match for session {session_id} at {first_match_at}")
        else:
            logger.info(f"No first match found yet for session {session_id}")

        refreshed_session = get_session(session_id)
        mark_job_done(
            job["id"],
            {
                "session_id": session_id,
                "first_match_at": refreshed_session["first_match_at"] if refreshed_session else None,
            },
        )

    async def _handle_session_finalize(self, job: dict):
        payload = job.get("payload_json") or {}

        report = self.pubg_service.build_session_report(
            pubg_handle=payload["pubg_handle"],
            started_at=payload["started_at"],
            ended_at=payload["ended_at"],
            first_match_at=payload.get("first_match_at"),
        )

        mark_job_done(job["id"], report)
        self._save_report_if_history_enabled(report, job)
        await self._post_session_report(report, job)

        logger.info(
            f"Session finalized for {payload['pubg_handle']} "
            f"with {report['total']['rounds']} games"
        )

    async def start(self):
        logger.info("PUBG job worker started")

        while True:
            cfg = get_runtime_config()
            idle_poll = float(cfg["pubg_job_worker_idle_poll_seconds"])

            job = get_next_job()
            if not job:
                await asyncio.sleep(idle_poll)
                continue

            try:
                mark_job_processing(job["id"])

                if job["job_type"] == "session_anchor":
                    await self._handle_session_anchor(job)

                elif job["job_type"] == "session_finalize":
                    await self._handle_session_finalize(job)

                elif job["job_type"] == "stats_lookup":
                    payload = job.get("payload_json") or {}
                    result = self.pubg_service.fetch_combined_stats(
                        payload["pubg_handle"]
                    )
                    mark_job_done(job["id"], result)

                else:
                    mark_job_failed(job["id"], f"Unknown job type: {job['job_type']}")

            except Exception as e:
                logger.exception("Job failed")
                mark_job_failed(job["id"], str(e))