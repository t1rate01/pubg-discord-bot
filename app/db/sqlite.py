import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "pubg_discord_bot.db"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracked_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_user_id TEXT UNIQUE NOT NULL,
                discord_name TEXT,
                pubg_handle TEXT,
                tracking_enabled INTEGER NOT NULL DEFAULT 0,
                history_enabled INTEGER NOT NULL DEFAULT 0,
                join_sound_enabled INTEGER NOT NULL DEFAULT 0,
                join_sound_path TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracking_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_user_id TEXT NOT NULL,
                discord_name TEXT,
                pubg_handle TEXT,
                voice_channel_id TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                first_match_at TEXT,
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pubg_request_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                discord_user_id TEXT,
                pubg_handle TEXT,
                session_id INTEGER,
                payload_json TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                priority INTEGER NOT NULL DEFAULT 0,
                result_json TEXT,
                error_text TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                finished_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER UNIQUE NOT NULL,
                discord_user_id TEXT NOT NULL,
                discord_name TEXT,
                pubg_handle TEXT NOT NULL,
                started_at TEXT NOT NULL,
                first_match_at TEXT,
                ended_at TEXT NOT NULL,
                total_rounds INTEGER NOT NULL DEFAULT 0,
                total_kills INTEGER NOT NULL DEFAULT 0,
                total_assists INTEGER NOT NULL DEFAULT 0,
                total_damage REAL NOT NULL DEFAULT 0,
                total_wins INTEGER NOT NULL DEFAULT 0,
                total_top10s INTEGER NOT NULL DEFAULT 0,
                total_kd REAL NOT NULL DEFAULT 0,
                total_kda REAL NOT NULL DEFAULT 0,
                total_avg_damage REAL NOT NULL DEFAULT 0,
                total_avg_placement REAL NOT NULL DEFAULT 0,
                ranked_rounds INTEGER NOT NULL DEFAULT 0,
                ranked_kills INTEGER NOT NULL DEFAULT 0,
                ranked_assists INTEGER NOT NULL DEFAULT 0,
                ranked_damage REAL NOT NULL DEFAULT 0,
                ranked_wins INTEGER NOT NULL DEFAULT 0,
                ranked_top10s INTEGER NOT NULL DEFAULT 0,
                ranked_kd REAL NOT NULL DEFAULT 0,
                ranked_kda REAL NOT NULL DEFAULT 0,
                ranked_avg_damage REAL NOT NULL DEFAULT 0,
                ranked_avg_placement REAL NOT NULL DEFAULT 0,
                normal_rounds INTEGER NOT NULL DEFAULT 0,
                normal_kills INTEGER NOT NULL DEFAULT 0,
                normal_assists INTEGER NOT NULL DEFAULT 0,
                normal_damage REAL NOT NULL DEFAULT 0,
                normal_wins INTEGER NOT NULL DEFAULT 0,
                normal_top10s INTEGER NOT NULL DEFAULT 0,
                normal_kd REAL NOT NULL DEFAULT 0,
                normal_kda REAL NOT NULL DEFAULT 0,
                normal_avg_damage REAL NOT NULL DEFAULT 0,
                normal_avg_placement REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_report_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_report_id INTEGER NOT NULL,
                match_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                game_mode TEXT,
                match_type TEXT,
                kills INTEGER NOT NULL DEFAULT 0,
                assists INTEGER NOT NULL DEFAULT 0,
                damage REAL NOT NULL DEFAULT 0,
                dbnos INTEGER NOT NULL DEFAULT 0,
                placement INTEGER NOT NULL DEFAULT 0,
                time_survived REAL NOT NULL DEFAULT 0,
                UNIQUE(session_report_id, match_id)
            )
        """)