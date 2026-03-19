from app.db.sqlite import get_connection


def save_session_report(
    session_id: int,
    discord_user_id: int,
    discord_name: str | None,
    pubg_handle: str,
    report: dict,
) -> int:
    total = report["total"]
    ranked = report["ranked"]
    normal = report["normal"]

    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO session_reports (
                session_id,
                discord_user_id,
                discord_name,
                pubg_handle,
                started_at,
                first_match_at,
                ended_at,
                total_rounds,
                total_kills,
                total_assists,
                total_damage,
                total_wins,
                total_top10s,
                total_kd,
                total_kda,
                total_avg_damage,
                total_avg_placement,
                ranked_rounds,
                ranked_kills,
                ranked_assists,
                ranked_damage,
                ranked_wins,
                ranked_top10s,
                ranked_kd,
                ranked_kda,
                ranked_avg_damage,
                ranked_avg_placement,
                normal_rounds,
                normal_kills,
                normal_assists,
                normal_damage,
                normal_wins,
                normal_top10s,
                normal_kd,
                normal_kda,
                normal_avg_damage,
                normal_avg_placement
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                str(discord_user_id),
                discord_name,
                pubg_handle,
                report["started_at"],
                report.get("first_match_at"),
                report["ended_at"],
                total["rounds"],
                total["kills"],
                total["assists"],
                total["damage"],
                total["wins"],
                total["top10s"],
                total["kd"],
                total["kda"],
                total["avg_damage"],
                total["avg_placement"],
                ranked["rounds"],
                ranked["kills"],
                ranked["assists"],
                ranked["damage"],
                ranked["wins"],
                ranked["top10s"],
                ranked["kd"],
                ranked["kda"],
                ranked["avg_damage"],
                ranked["avg_placement"],
                normal["rounds"],
                normal["kills"],
                normal["assists"],
                normal["damage"],
                normal["wins"],
                normal["top10s"],
                normal["kd"],
                normal["kda"],
                normal["avg_damage"],
                normal["avg_placement"],
            ),
        )

        row = conn.execute(
            """
            SELECT id
            FROM session_reports
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

        return row["id"]


def save_session_report_matches(session_report_id: int, games: list[dict]) -> None:
    with get_connection() as conn:
        for game in games:
            conn.execute(
                """
                INSERT OR REPLACE INTO session_report_matches (
                    session_report_id,
                    match_id,
                    created_at,
                    game_mode,
                    match_type,
                    kills,
                    assists,
                    damage,
                    dbnos,
                    placement,
                    time_survived
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_report_id,
                    game["match_id"],
                    game["created_at"],
                    game["game_mode"],
                    game["match_type"],
                    game["kills"],
                    game["assists"],
                    game["damage"],
                    game["dbnos"],
                    game["placement"],
                    game["time_survived"],
                ),
            )