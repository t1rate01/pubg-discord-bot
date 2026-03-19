import requests
from datetime import datetime, timezone

from app.db.models import get_runtime_config
from app.worker.rate_limiter import PubgRateLimiter


BASE_URL = "https://api.pubg.com"
ALLOWED_GAME_MODES = {
    "solo",
    "solo-fpp",
    "duo",
    "duo-fpp",
    "squad",
    "squad-fpp",
}


def parse_pubg_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return float(numerator)
    return numerator / denominator


def calc_kd(kills: int, deaths: int) -> float:
    return safe_div(kills, max(1, deaths))


def calc_kda(kills: int, assists: int, deaths: int) -> float:
    return safe_div(kills + assists, max(1, deaths))


def summarize_mode(mode_stats: dict) -> dict:
    rounds = mode_stats.get("roundsPlayed", 0)
    kills = mode_stats.get("kills", 0)
    assists = mode_stats.get("assists", 0)
    wins = mode_stats.get("wins", 0)
    top10s = mode_stats.get("top10s", 0)
    damage = mode_stats.get("damageDealt", 0)
    losses = mode_stats.get("losses", rounds)

    return {
        "rounds": rounds,
        "kills": kills,
        "assists": assists,
        "wins": wins,
        "top10s": top10s,
        "damage": damage,
        "kd": calc_kd(kills, losses),
        "kda": calc_kda(kills, assists, losses),
        "avg_damage": safe_div(damage, rounds) if rounds > 0 else 0,
    }


def summarize_ranked_mode(mode_stats: dict) -> dict:
    rounds = mode_stats.get("roundsPlayed", 0)
    kills = mode_stats.get("kills", 0)
    assists = mode_stats.get("assists", 0)
    damage = mode_stats.get("damageDealt", 0)
    deaths = mode_stats.get("deaths", rounds)
    wins = mode_stats.get("wins", 0)

    return {
        "rounds": rounds,
        "kills": kills,
        "assists": assists,
        "wins": wins,
        "damage": damage,
        "kd": calc_kd(kills, deaths),
        "kda": calc_kda(kills, assists, deaths),
        "avg_damage": safe_div(damage, rounds) if rounds > 0 else 0,
        "current_tier": mode_stats.get("currentTier", {}),
        "best_tier": mode_stats.get("bestTier", {}),
        "current_rank_point": mode_stats.get("currentRankPoint", 0),
        "best_rank_point": mode_stats.get("bestRankPoint", 0),
        "avg_rank": mode_stats.get("avgRank", 0),
        "top10_ratio": mode_stats.get("top10Ratio", 0),
        "win_ratio": mode_stats.get("winRatio", 0),
    }


class PubgService:
    def __init__(self):
        cfg = get_runtime_config()
        self.api_key = cfg["pubg_api_key"]
        self.shard = "steam"
        self.limiter = PubgRateLimiter(
            max_requests=int(cfg["pubg_rate_limit_max_requests"]),
            window_seconds=int(cfg["pubg_rate_limit_window_seconds"]),
        )

    def _headers(self):
        if not self.api_key:
            raise RuntimeError("PUBG API key is not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/vnd.api+json",
        }

    def _request_json(self, url: str, params: dict | None = None) -> dict:
        last_error = None

        for attempt in range(2):
            self.limiter.wait_if_needed()

            response = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )

            self.limiter.update_from_response(response)

            if response.status_code == 429:
                last_error = RuntimeError("PUBG API rate limit hit (429)")
                if attempt == 0:
                    self.limiter.handle_429_and_wait(response)
                    continue
                raise last_error

            response.raise_for_status()
            return response.json()

        if last_error:
            raise last_error

        raise RuntimeError("Unexpected PUBG API request failure")

    def get_player(self, name: str) -> dict:
        url = f"{BASE_URL}/shards/{self.shard}/players"
        data = self._request_json(url, params={"filter[playerNames]": name})["data"]

        if not data:
            raise RuntimeError(f"No PUBG player found for handle '{name}'")

        return data[0]

    def get_season_id(self) -> str:
        url = f"{BASE_URL}/shards/{self.shard}/seasons"
        data = self._request_json(url)

        for s in data["data"]:
            attrs = s["attributes"]
            if attrs.get("isCurrentSeason") and not attrs.get("isOffseason"):
                return s["id"]

        raise RuntimeError("No current season found")

    def get_stats(self, player_id: str, season_id: str) -> dict:
        url = f"{BASE_URL}/shards/{self.shard}/players/{player_id}/seasons/{season_id}"
        return self._request_json(url)

    def get_ranked(self, player_id: str, season_id: str) -> dict:
        url = f"{BASE_URL}/shards/{self.shard}/players/{player_id}/seasons/{season_id}/ranked"
        return self._request_json(url)

    def get_match(self, match_id: str) -> dict:
        url = f"{BASE_URL}/shards/{self.shard}/matches/{match_id}"
        return self._request_json(url)

    def fetch_combined_stats(self, name: str) -> dict:
        player = self.get_player(name)
        pid = player["id"]
        season_id = self.get_season_id()
        stats = self.get_stats(pid, season_id)
        ranked = self.get_ranked(pid, season_id)

        return {
            "player": player["attributes"]["name"],
            "season_id": season_id,
            "stats": stats,
            "ranked": ranked,
            "parsed": self.build_stats_embed_data({
                "player": player["attributes"]["name"],
                "stats": stats,
                "ranked": ranked,
            }),
        }

    def _extract_recent_match_ids(self, player: dict) -> list[str]:
        relationships = player.get("relationships", {})
        matches = relationships.get("matches", {}).get("data", [])
        return [item["id"] for item in matches]

    def _extract_participant_stats(self, match_data: dict, pubg_handle: str) -> dict | None:
        included = match_data.get("included", [])
        target = pubg_handle.lower()

        for item in included:
            if item.get("type") != "participant":
                continue

            stats = item.get("attributes", {}).get("stats", {})
            name = str(stats.get("name", "")).lower()

            if name == target:
                return stats

        return None

    def find_first_session_match_time(self, pubg_handle: str, started_at: str) -> str | None:
        player = self.get_player(pubg_handle)
        recent_match_ids = self._extract_recent_match_ids(player)
        start_dt = parse_pubg_ts(started_at)

        valid_match_times = []

        for match_id in recent_match_ids:
            match_data = self.get_match(match_id)
            match_attrs = match_data["data"]["attributes"]

            created_at = parse_pubg_ts(match_attrs["createdAt"])
            game_mode = match_attrs.get("gameMode")
            is_custom = match_attrs.get("isCustomMatch", False)

            if created_at < start_dt:
                continue
            if is_custom:
                continue
            if game_mode not in ALLOWED_GAME_MODES:
                continue

            stats = self._extract_participant_stats(match_data, pubg_handle)
            if not stats:
                continue

            valid_match_times.append(match_attrs["createdAt"])

        if not valid_match_times:
            return None

        return sorted(valid_match_times)[0]

    def build_session_report(
        self,
        pubg_handle: str,
        started_at: str,
        ended_at: str,
        first_match_at: str | None = None,
    ) -> dict:
        player = self.get_player(pubg_handle)
        recent_match_ids = self._extract_recent_match_ids(player)

        lower_bound = parse_pubg_ts(first_match_at) if first_match_at else parse_pubg_ts(started_at)
        end_dt = parse_pubg_ts(ended_at)

        matched_games = []

        for match_id in recent_match_ids:
            match_data = self.get_match(match_id)
            match_attrs = match_data["data"]["attributes"]

            game_mode = match_attrs.get("gameMode")
            match_type = match_attrs.get("matchType", "unknown")
            is_custom = match_attrs.get("isCustomMatch", False)
            created_at = parse_pubg_ts(match_attrs["createdAt"])

            if created_at < lower_bound or created_at > end_dt:
                continue
            if is_custom:
                continue
            if game_mode not in ALLOWED_GAME_MODES:
                continue

            stats = self._extract_participant_stats(match_data, pubg_handle)
            if not stats:
                continue

            matched_games.append({
                "match_id": match_id,
                "created_at": match_attrs["createdAt"],
                "game_mode": game_mode,
                "match_type": match_type,
                "kills": stats.get("kills", 0),
                "assists": stats.get("assists", 0),
                "damage": stats.get("damageDealt", 0),
                "dbnos": stats.get("DBNOs", 0),
                "placement": stats.get("winPlace", 0),
                "time_survived": stats.get("timeSurvived", 0),
            })

        def aggregate(games: list[dict]) -> dict:
            rounds = len(games)
            kills = sum(g["kills"] for g in games)
            assists = sum(g["assists"] for g in games)
            damage = sum(g["damage"] for g in games)
            wins = sum(1 for g in games if g["placement"] == 1)
            top10s = sum(1 for g in games if g["placement"] <= 10)
            avg_placement = safe_div(sum(g["placement"] for g in games), rounds) if rounds else 0

            return {
                "rounds": rounds,
                "kills": kills,
                "assists": assists,
                "damage": damage,
                "wins": wins,
                "top10s": top10s,
                "kd": calc_kd(kills, rounds),
                "kda": calc_kda(kills, assists, rounds),
                "avg_damage": safe_div(damage, rounds) if rounds else 0,
                "avg_placement": avg_placement,
            }

        ranked_games = [g for g in matched_games if g["match_type"] == "competitive"]
        normal_games = [g for g in matched_games if g["match_type"] != "competitive"]

        return {
            "player": pubg_handle,
            "started_at": started_at,
            "first_match_at": first_match_at,
            "ended_at": ended_at,
            "total": aggregate(matched_games),
            "ranked": aggregate(ranked_games),
            "normal": aggregate(normal_games),
            "games": matched_games,
        }

    def build_stats_embed_data(self, result: dict) -> dict:
        normal_modes = result["stats"]["data"]["attributes"]["gameModeStats"]
        ranked_modes = result["ranked"]["data"]["attributes"].get("rankedGameModeStats", {})

        solo_fpp = summarize_mode(normal_modes.get("solo-fpp", {}))
        duo_fpp = summarize_mode(normal_modes.get("duo-fpp", {}))
        squad_fpp = summarize_mode(normal_modes.get("squad-fpp", {}))

        ranked_duo = summarize_ranked_mode(ranked_modes.get("duo-fpp", {}))
        ranked_squad = summarize_ranked_mode(ranked_modes.get("squad-fpp", {}))

        normal_rounds = solo_fpp["rounds"] + duo_fpp["rounds"] + squad_fpp["rounds"]
        normal_kills = solo_fpp["kills"] + duo_fpp["kills"] + squad_fpp["kills"]
        normal_assists = solo_fpp["assists"] + duo_fpp["assists"] + squad_fpp["assists"]
        normal_losses = max(1, normal_rounds - (solo_fpp["wins"] + duo_fpp["wins"] + squad_fpp["wins"]))
        normal_damage = solo_fpp["damage"] + duo_fpp["damage"] + squad_fpp["damage"]

        ranked_rounds = ranked_duo["rounds"] + ranked_squad["rounds"]
        ranked_kills = ranked_duo["kills"] + ranked_squad["kills"]
        ranked_assists = ranked_duo["assists"] + ranked_squad["assists"]
        ranked_damage = ranked_duo["damage"] + ranked_squad["damage"]
        ranked_deaths = max(1, ranked_rounds)

        return {
            "player_name": result["player"],
            "solo_fpp": solo_fpp,
            "duo_fpp": duo_fpp,
            "squad_fpp": squad_fpp,
            "ranked_duo": ranked_duo,
            "ranked_squad": ranked_squad,
            "normal_rounds": normal_rounds,
            "normal_kills": normal_kills,
            "normal_assists": normal_assists,
            "normal_losses": normal_losses,
            "normal_damage": normal_damage,
            "ranked_rounds": ranked_rounds,
            "ranked_kills": ranked_kills,
            "ranked_assists": ranked_assists,
            "ranked_damage": ranked_damage,
            "ranked_deaths": ranked_deaths,
        }