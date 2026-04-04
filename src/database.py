"""SQLite 数据库操作：建表、upsert、查询、聚合。"""

import sqlite3
from datetime import datetime, timedelta
from src.config import DB_PATH, BEIJING_TZ


def _migrate_columns(conn):
    """安全地为已有表添加新列。"""
    new_daily_cols = [
        ("sleep_cycle_count", "REAL"), ("disturbance_count", "REAL"),
        ("sleep_consistency", "REAL"),
        ("sleep_need_baseline_min", "REAL"), ("sleep_need_debt_min", "REAL"),
        ("sleep_need_strain_min", "REAL"), ("sleep_need_nap_min", "REAL"),
    ]
    new_workout_cols = [
        ("altitude_gain_m", "REAL"), ("kilojoules", "REAL"),
        ("zone_0_min", "REAL"), ("zone_1_min", "REAL"), ("zone_2_min", "REAL"),
        ("zone_3_min", "REAL"), ("zone_4_min", "REAL"), ("zone_5_min", "REAL"),
    ]
    for col, typ in new_daily_cols:
        try:
            conn.execute(f"ALTER TABLE daily ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # 列已存在
    for col, typ in new_workout_cols:
        try:
            conn.execute(f"ALTER TABLE workouts ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """建表（如不存在）。"""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily (
                date TEXT PRIMARY KEY,
                recovery_score REAL,
                hrv REAL,
                resting_hr REAL,
                spo2 REAL,
                skin_temp REAL,
                sleep_total_min REAL,
                sleep_deep_min REAL,
                sleep_rem_min REAL,
                sleep_light_min REAL,
                sleep_awake_min REAL,
                sleep_cycle_count REAL,
                disturbance_count REAL,
                sleep_performance REAL,
                sleep_consistency REAL,
                sleep_efficiency REAL,
                respiratory_rate REAL,
                sleep_need_baseline_min REAL,
                sleep_need_debt_min REAL,
                sleep_need_strain_min REAL,
                sleep_need_nap_min REAL,
                strain REAL,
                avg_hr REAL,
                max_hr REAL,
                kilojoules REAL,
                updated_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id TEXT PRIMARY KEY,
                date TEXT,
                sport_name TEXT,
                strain REAL,
                avg_hr REAL,
                max_hr REAL,
                distance_m REAL,
                altitude_gain_m REAL,
                duration_min REAL,
                kilojoules REAL,
                zone_0_min REAL,
                zone_1_min REAL,
                zone_2_min REAL,
                zone_3_min REAL,
                zone_4_min REAL,
                zone_5_min REAL,
                updated_at TEXT
            )
        """)
        # 迁移：为已有数据库添加新列（ALTER TABLE ADD COLUMN 对缺失列安全）
        _migrate_columns(conn)


def upsert_day(row: dict):
    """插入或更新一天的数据。"""
    row["updated_at"] = datetime.now(BEIJING_TZ).isoformat()
    cols = list(row.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    with _conn() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO daily ({col_names}) VALUES ({placeholders})",
            [row[c] for c in cols],
        )


def upsert_workout(row: dict):
    """插入或更新一条锻炼记录。"""
    row["updated_at"] = datetime.now(BEIJING_TZ).isoformat()
    cols = list(row.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    with _conn() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO workouts ({col_names}) VALUES ({placeholders})",
            [row[c] for c in cols],
        )


def get_recent_days(n: int = 7) -> list:
    """获取最近 n 天的数据（按日期降序）。"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM daily ORDER BY date DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_days_in_range(start_date: str, end_date: str) -> list:
    """获取日期范围内的数据（升序）。"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM daily WHERE date >= ? AND date <= ? ORDER BY date ASC",
            (start_date, end_date),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_daily() -> list:
    """获取全部每日数据（升序）。"""
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM daily ORDER BY date ASC").fetchall()
    return [dict(r) for r in rows]


def get_all_workouts() -> list:
    """获取全部锻炼记录（升序）。"""
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM workouts ORDER BY date ASC").fetchall()
    return [dict(r) for r in rows]


def get_recent_workouts(n_days: int = 7) -> list:
    """获取最近 n 天内的锻炼记录（按日期降序）。"""
    cutoff = (datetime.now(BEIJING_TZ) - timedelta(days=n_days)).strftime("%Y-%m-%d")
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM workouts WHERE date >= ? ORDER BY date DESC", (cutoff,)
        ).fetchall()
    return [dict(r) for r in rows]


def checkpoint():
    """强制 WAL checkpoint，确保所有写入对新连接可见。"""
    with _conn() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def today_beijing() -> str:
    """当前北京时间日期字符串。"""
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
