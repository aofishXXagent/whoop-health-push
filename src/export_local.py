#!/usr/bin/env python3
"""
Local WHOOP Data Export

Standalone script for local use — no Feishu/MiniMax dependencies.
Uses token_manager for safe credential handling.

Usage:
    python3 -m src.export_local              # Export to data/ directory
    WHOOP_CRED_PATH=./creds.json python3 -m src.export_local  # Custom cred path
"""

import csv
import os
from datetime import datetime

from src.token_manager import get_headers, fetch_paginated

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(OUT_DIR, exist_ok=True)


def export_recovery(headers):
    print("\n--- Recovery ---")
    records = fetch_paginated("recovery", headers=headers, max_records=25)
    if not records:
        print("  No records")
        return
    path = os.path.join(OUT_DIR, "recovery.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "date", "cycle_id", "recovery_score", "hrv_rmssd_milli",
            "resting_heart_rate", "spo2_percentage", "skin_temp_celsius",
            "score_state", "created_at",
        ])
        for r in records:
            score = r.get("score", {}) or {}
            created = r.get("created_at", "")
            w.writerow([
                created[:10], r.get("cycle_id", ""),
                score.get("recovery_score", ""), score.get("hrv_rmssd_milli", ""),
                score.get("resting_heart_rate", ""), score.get("spo2_percentage", ""),
                score.get("skin_temp_celsius", ""), r.get("score_state", ""), created,
            ])
    print(f"  -> {len(records)} records saved to {path}")


def export_sleep(headers):
    print("\n--- Sleep ---")
    records = fetch_paginated("activity/sleep", headers=headers, max_records=25)
    if not records:
        print("  No records")
        return
    ms_to_min = lambda ms: round(ms / 60000, 1) if ms else ""
    path = os.path.join(OUT_DIR, "sleep.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "date", "sleep_id", "start", "end",
            "total_in_bed_min", "total_awake_min", "light_sleep_min",
            "deep_sleep_min", "rem_sleep_min",
            "sleep_cycles", "disturbances", "respiratory_rate",
            "sleep_performance_pct", "sleep_consistency_pct", "sleep_efficiency_pct",
            "baseline_need_min", "sleep_debt_need_min", "strain_need_min",
            "score_state", "nap",
        ])
        for r in records:
            score = r.get("score", {}) or {}
            stage = score.get("stage_summary", {}) or {}
            need = score.get("sleep_needed", {}) or {}
            start = r.get("start", "")
            w.writerow([
                start[:10], r.get("id", ""), start, r.get("end", ""),
                ms_to_min(stage.get("total_in_bed_time_milli")),
                ms_to_min(stage.get("total_awake_time_milli")),
                ms_to_min(stage.get("total_light_sleep_time_milli")),
                ms_to_min(stage.get("total_slow_wave_sleep_time_milli")),
                ms_to_min(stage.get("total_rem_sleep_time_milli")),
                stage.get("sleep_cycle_count", ""), stage.get("disturbance_count", ""),
                score.get("respiratory_rate", ""),
                score.get("sleep_performance_percentage", ""),
                score.get("sleep_consistency_percentage", ""),
                score.get("sleep_efficiency_percentage", ""),
                ms_to_min(need.get("baseline_milli")),
                ms_to_min(need.get("need_from_sleep_debt_milli")),
                ms_to_min(need.get("need_from_recent_strain_milli")),
                r.get("score_state", ""), r.get("nap", False),
            ])
    print(f"  -> {len(records)} records saved to {path}")


def export_cycles(headers):
    print("\n--- Cycles ---")
    records = fetch_paginated("cycle", headers=headers, max_records=25)
    if not records:
        print("  No records")
        return
    path = os.path.join(OUT_DIR, "cycles.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "date", "cycle_id", "start", "end",
            "strain", "avg_heart_rate", "max_heart_rate", "kilojoules",
            "score_state",
        ])
        for r in records:
            score = r.get("score", {}) or {}
            start = r.get("start", "")
            w.writerow([
                start[:10], r.get("id", ""), start, r.get("end", ""),
                score.get("strain", ""), score.get("average_heart_rate", ""),
                score.get("max_heart_rate", ""), score.get("kilojoule", ""),
                r.get("score_state", ""),
            ])
    print(f"  -> {len(records)} records saved to {path}")


def export_workouts(headers):
    print("\n--- Workouts ---")
    records = fetch_paginated("activity/workout", headers=headers, max_records=50)
    if not records:
        print("  No records")
        return
    path = os.path.join(OUT_DIR, "workouts.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "date", "workout_id", "sport_id", "start", "end",
            "strain", "avg_heart_rate", "max_heart_rate", "kilojoules",
            "distance_meter", "altitude_gain_meter", "score_state",
        ])
        for r in records:
            score = r.get("score", {}) or {}
            start = r.get("start", "")
            w.writerow([
                start[:10], r.get("id", ""), r.get("sport_id", ""),
                start, r.get("end", ""),
                score.get("strain", ""), score.get("average_heart_rate", ""),
                score.get("max_heart_rate", ""), score.get("kilojoule", ""),
                score.get("distance_meter", ""), score.get("altitude_gain_meter", ""),
                r.get("score_state", ""),
            ])
    print(f"  -> {len(records)} records saved to {path}")


def main():
    print(f"=== WHOOP Data Export — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    headers = get_headers()

    export_recovery(headers)
    export_sleep(headers)
    export_cycles(headers)
    export_workouts(headers)

    print(f"\n=== Done! Files in: {OUT_DIR} ===")


if __name__ == "__main__":
    main()
