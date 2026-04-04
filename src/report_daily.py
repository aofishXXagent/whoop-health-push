"""每日健康晨报：拉数据 → 存DB → AI生成报告 → 推飞书 → 更新Excel。"""

import json
from datetime import datetime
from src import config
from src.database import init_db, upsert_day, upsert_workout, get_recent_days, get_recent_workouts, today_beijing, checkpoint
from src.whoop_client import WhoopClient
from src.feishu_client import FeishuClient
from src.minimax_client import MinimaxClient
from src.excel_manager import rebuild_excel
from src.github_secrets import rotate_secrets


# ── WHOOP 数据解析 ───────────────────────────────────────────────────────────

def _parse_date(iso_str):
    if not iso_str:
        return None
    return iso_str[:10]


def _ms_to_min(ms):
    if ms is None:
        return None
    return round(ms / 60_000, 1)


def _parse_recovery(rec: dict) -> dict:
    score = rec.get("score", {})
    return {
        "recovery_score": score.get("recovery_score"),
        "hrv": score.get("hrv_rmssd_milli"),
        "resting_hr": score.get("resting_heart_rate"),
        "spo2": score.get("spo2_percentage"),
        "skin_temp": score.get("skin_temp_celsius"),
    }


def _parse_sleep(sleep: dict) -> dict:
    score = sleep.get("score", {})
    stage = score.get("stage_summary", {})
    need = score.get("sleep_needed", {})
    return {
        "sleep_total_min": _ms_to_min(stage.get("total_in_bed_time_milli")),
        "sleep_deep_min": _ms_to_min(stage.get("total_slow_wave_sleep_time_milli")),
        "sleep_rem_min": _ms_to_min(stage.get("total_rem_sleep_time_milli")),
        "sleep_light_min": _ms_to_min(stage.get("total_light_sleep_time_milli")),
        "sleep_awake_min": _ms_to_min(stage.get("total_awake_time_milli")),
        "sleep_cycle_count": stage.get("sleep_cycle_count"),
        "disturbance_count": stage.get("disturbance_count"),
        "sleep_performance": score.get("sleep_performance_percentage"),
        "sleep_consistency": score.get("sleep_consistency_percentage"),
        "sleep_efficiency": score.get("sleep_efficiency_percentage"),
        "respiratory_rate": score.get("respiratory_rate"),
        "sleep_need_baseline_min": _ms_to_min(need.get("baseline_milli")),
        "sleep_need_debt_min": _ms_to_min(need.get("need_from_sleep_debt_milli")),
        "sleep_need_strain_min": _ms_to_min(need.get("need_from_recent_strain_milli")),
        "sleep_need_nap_min": _ms_to_min(need.get("need_from_recent_nap_milli")),
    }


def _parse_cycle(cycle: dict) -> dict:
    score = cycle.get("score", {})
    return {
        "strain": score.get("strain"),
        "avg_hr": score.get("average_heart_rate"),
        "max_hr": score.get("max_heart_rate"),
        "kilojoules": score.get("kilojoule"),
    }


def _parse_workout(w: dict) -> dict:
    score = w.get("score", {})
    zones = score.get("zone_durations", {}) or {}
    return {
        "id": str(w.get("id", "")),
        "date": _parse_date(w.get("start")),
        "sport_name": w.get("sport_name") or str(w.get("sport_id", "Unknown")),
        "strain": score.get("strain"),
        "avg_hr": score.get("average_heart_rate"),
        "max_hr": score.get("max_heart_rate"),
        "distance_m": score.get("distance_meter"),
        "altitude_gain_m": score.get("altitude_gain_meter"),
        "duration_min": _ms_to_min(score.get("duration_milli")),
        "kilojoules": score.get("kilojoule"),
        "zone_0_min": _ms_to_min(zones.get("zone_zero_milli")),
        "zone_1_min": _ms_to_min(zones.get("zone_one_milli")),
        "zone_2_min": _ms_to_min(zones.get("zone_two_milli")),
        "zone_3_min": _ms_to_min(zones.get("zone_three_milli")),
        "zone_4_min": _ms_to_min(zones.get("zone_four_milli")),
        "zone_5_min": _ms_to_min(zones.get("zone_five_milli")),
    }


# ── 数据同步 ─────────────────────────────────────────────────────────────────

def sync_whoop_data(whoop: WhoopClient):
    """从 WHOOP 拉最近数据并存入 SQLite。"""
    # 恢复数据
    recoveries = whoop.fetch_recoveries(limit=10)
    recovery_by_date = {}
    for r in recoveries:
        date = _parse_date(r.get("created_at"))
        if date:
            recovery_by_date[date] = _parse_recovery(r)

    # 睡眠数据（用 end 即醒来时间作为日期，与 recovery 的 created_at 对齐）
    sleeps = whoop.fetch_sleeps(limit=10)
    sleep_by_date = {}
    for s in sleeps:
        date = _parse_date(s.get("end") or s.get("start"))
        if date:
            sleep_by_date[date] = _parse_sleep(s)

    # 压力/周期数据
    cycles = whoop.fetch_cycles(limit=10)
    cycle_by_date = {}
    for c in cycles:
        date = _parse_date(c.get("start"))
        if date:
            cycle_by_date[date] = _parse_cycle(c)

    # 调试：打印 API 返回的日期范围
    print(f"[Sync] Recovery dates: {sorted(recovery_by_date.keys())}")
    print(f"[Sync] Sleep dates: {sorted(sleep_by_date.keys())}")
    print(f"[Sync] Cycle dates: {sorted(cycle_by_date.keys())}")

    # 合并并写入
    all_dates = set(recovery_by_date) | set(sleep_by_date) | set(cycle_by_date)
    for date in sorted(all_dates):
        row = {"date": date}
        row.update(recovery_by_date.get(date, {}))
        row.update(sleep_by_date.get(date, {}))
        row.update(cycle_by_date.get(date, {}))
        upsert_day(row)

    # 锻炼数据
    workouts = whoop.fetch_workouts(limit=50)
    for w in workouts:
        parsed = _parse_workout(w)
        if parsed["id"] and parsed["date"]:
            upsert_workout(parsed)

    # 强制 WAL checkpoint，确保后续读取能看到所有写入
    checkpoint()
    print(f"[Sync] {len(all_dates)} days + {len(workouts)} workouts synced")


# ── AI 报告生成 ──────────────────────────────────────────────────────────────

DAILY_SYSTEM_PROMPT = """你是用户的私人健康教练。用户戴着 WHOOP 手环，每周跑步 2-3 次，对健康数据是新手。

你收到的数据中包含已预计算好的洞察（百分比变化、异常标记、趋势方向）。你的任务是把这些转化为用户早上能直接用来规划一天的建议。

## 用户是谁
- 有氧运动者（主要跑步），每周 2-3 次
- WHOOP 小白：提到 HRV/Strain 等专业概念时，用一句话解释它代表什么
- 关注四件事：今天该不该运动、精力怎么分配、昨晚睡得好不好、身体在变好还是变差
- 也关注压力管理：希望知道身体承受了多少压力、怎么缓解、找到个人规律

## 输出结构（严格按此格式，用分隔线分段）

━━━ 健康晨报 · {日期} ━━━

⚡ 今日一句话
用 1 句话概括今天的身体状态和最该做的一件事。这是全文最重要的一句话。

😴 昨晚睡眠
告诉用户"睡得好不好"以及"为什么"。必须覆盖：
- 睡够了吗（实际时长 vs 身体需求，数据中已算好缺口）
- 睡深了吗（深睡/REM 占比是否达标，数据中已标注）
- 睡稳了吗（干扰次数、效率）
- 今晚怎么改善（1 条具体行动）

💚 今天的身体
用人话解释核心指标：
- 恢复分 = 身体电量（绿区满电/黄区半电/红区快没电）
- HRV = 神经系统弹性（高=身体放松恢复好，低=还在紧绷）
- 静息心率（高于平均可能意味着疲劳或脱水）
每个指标必须引用数据中的"vs 7天均值"变化。

🏃 运动建议
结合近期运动记录（数据中有具体的运动类型、心率、距离）和今天的恢复状态：
- 回顾最近的训练负荷（如"前天跑步 strain 14.6，昨天骑行 strain 4.2"）
- 今天适合什么强度（高/中/低/休息）
- 具体建议（如"轻松跑 30 分钟，心率控制在 130 以下"）
- 如果不适合运动，给替代方案（散步/拉伸/瑜伽）

🧠 精力与压力
- 根据恢复和 HRV，建议今天的工作节奏（适合冲刺还是放松）
- 如果压力指标偏高，给 1 条具体减压行动（如"下午 3 点散步 15 分钟"）

📈 本周趋势
用 2-3 句话说明：这一周身体是在变好还是变差？为什么？（引用趋势方向数据）

## 写作规则
- 总字数 400-600 字，能在手机一屏半内读完
- 简洁专业，适当使用 emoji 让阅读更轻松（每个段落标题用 1 个 emoji），不说废话套话
- 每个结论必须引用数据中的具体数值
- 不编造数据，数据缺失时写"暂无"
- 不过度解读正常范围内的波动，不吓人
- 用户是小白：首次出现专业术语时用括号加一句解释
"""


def _fmt(v, unit: str = "") -> str:
    if v is None:
        return "暂无"
    if isinstance(v, float):
        return f"{v:.1f}{unit}"
    return f"{v}{unit}"


def _pct_change(current, baseline):
    """计算相对基线的百分比变化，返回字符串描述。"""
    if current is None or baseline is None or baseline == 0:
        return None
    change = ((current - baseline) / baseline) * 100
    if abs(change) < 1:
        return "持平"
    direction = "↑" if change > 0 else "↓"
    return f"{direction}{abs(change):.1f}%"


def _trend_direction(values):
    """判断一组值的趋势方向（至少3个有效值）。"""
    valid = [v for v in values if v is not None]
    if len(valid) < 3:
        return "数据不足"
    first_half = sum(valid[:len(valid)//2]) / (len(valid)//2)
    second_half = sum(valid[len(valid)//2:]) / (len(valid) - len(valid)//2)
    diff = ((second_half - first_half) / first_half) * 100 if first_half else 0
    if diff > 5:
        return "上升趋势"
    elif diff < -5:
        return "下降趋势"
    return "基本稳定"


def _find_best_today(recent: list) -> dict:
    """找最新的有恢复分的一天（睡眠数据WHOOP有约1天延迟，不强制要求）。"""
    for day in recent:
        if day.get("recovery_score") is not None:
            return day
    return recent[0] if recent else {}


def _build_daily_prompt(today_data: dict, recent_7: list, workouts: list = None) -> str:
    """构建给 AI 的用户 prompt：原始数据 + 预计算洞察 + 异常标记 + 运动记录。"""
    d = today_data
    lines = []

    # ── 基础数据 ──
    lines.append(f"=== 当日数据（{d.get('date', '未知')}）===")
    lines.append(f"恢复分：{_fmt(d.get('recovery_score'), '%')}")
    lines.append(f"HRV：{_fmt(d.get('hrv'), ' ms')}")
    lines.append(f"静息心率：{_fmt(d.get('resting_hr'), ' bpm')}")
    lines.append(f"血氧：{_fmt(d.get('spo2'), '%')}")
    lines.append(f"皮肤温度：{_fmt(d.get('skin_temp'), ' °C')}")

    lines.append("")
    lines.append("--- 睡眠详情 ---")
    sleep_total = d.get("sleep_total_min")
    sleep_deep = d.get("sleep_deep_min")
    sleep_rem = d.get("sleep_rem_min")
    lines.append(f"总时长：{_fmt(sleep_total, ' min')}（{_fmt(round(sleep_total/60, 1) if sleep_total else None, ' h')}）")
    lines.append(f"深睡：{_fmt(sleep_deep, ' min')}")
    lines.append(f"REM：{_fmt(sleep_rem, ' min')}")
    lines.append(f"浅睡：{_fmt(d.get('sleep_light_min'), ' min')}")
    lines.append(f"清醒：{_fmt(d.get('sleep_awake_min'), ' min')}")
    lines.append(f"睡眠周期数：{_fmt(d.get('sleep_cycle_count'))}")
    lines.append(f"干扰次数：{_fmt(d.get('disturbance_count'))}")
    lines.append(f"睡眠效率：{_fmt(d.get('sleep_efficiency'), '%')}")
    lines.append(f"睡眠表现：{_fmt(d.get('sleep_performance'), '%')}")
    lines.append(f"睡眠一致性：{_fmt(d.get('sleep_consistency'), '%')}")
    lines.append(f"呼吸频率：{_fmt(d.get('respiratory_rate'), ' 次/min')}")

    # 睡眠占比（预计算）
    if sleep_total and sleep_total > 0:
        if sleep_deep:
            deep_pct = round(sleep_deep / sleep_total * 100, 1)
            flag = " [偏低]" if deep_pct < 15 else (" [优秀]" if deep_pct > 20 else " [正常]")
            lines.append(f"深睡占比：{deep_pct}%{flag}（理想 15-20%）")
        if sleep_rem:
            rem_pct = round(sleep_rem / sleep_total * 100, 1)
            flag = " [偏低]" if rem_pct < 20 else (" [优秀]" if rem_pct > 25 else " [正常]")
            lines.append(f"REM占比：{rem_pct}%{flag}（理想 20-25%）")

    # 睡眠需求 vs 实际（预计算）
    baseline_need = d.get("sleep_need_baseline_min")
    debt_need = d.get("sleep_need_debt_min")
    strain_need = d.get("sleep_need_strain_min")
    if baseline_need:
        total_need = baseline_need + (debt_need or 0) + (strain_need or 0)
        lines.append(f"身体总睡眠需求：{total_need:.0f} min（基线 {baseline_need:.0f} + 睡眠债 {_fmt(debt_need, '')} + 压力补偿 {_fmt(strain_need, '')}）")
        if sleep_total:
            gap = sleep_total - total_need
            if gap < -30:
                lines.append(f"[睡眠缺口] 少睡了 {abs(gap):.0f} 分钟，今晚建议补回")
            elif gap > 30:
                lines.append(f"[睡眠充足] 多睡了 {gap:.0f} 分钟")
            else:
                lines.append(f"[睡眠刚好] 基本满足身体需求")

    lines.append("")
    lines.append("--- 压力/活动 ---")
    lines.append(f"压力分(Strain)：{_fmt(d.get('strain'))}")
    lines.append(f"平均心率：{_fmt(d.get('avg_hr'), ' bpm')}")
    lines.append(f"最大心率：{_fmt(d.get('max_hr'), ' bpm')}")
    lines.append(f"能量消耗：{_fmt(d.get('kilojoules'), ' kJ')}")

    # ── 7天均值与对比 ──
    def avg(key):
        vals = [r[key] for r in recent_7 if r.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    avg_recovery = avg("recovery_score")
    avg_hrv = avg("hrv")
    avg_sleep = avg("sleep_total_min")
    avg_deep = avg("sleep_deep_min")
    avg_rhr = avg("resting_hr")
    avg_strain = avg("strain")

    lines.append("")
    lines.append("=== 预计算洞察（vs 7天均值）===")
    lines.append(f"恢复分：{_fmt(d.get('recovery_score'))} vs 均值 {_fmt(avg_recovery)} → {_pct_change(d.get('recovery_score'), avg_recovery) or '无法计算'}")
    lines.append(f"HRV：{_fmt(d.get('hrv'), ' ms')} vs 均值 {_fmt(avg_hrv, ' ms')} → {_pct_change(d.get('hrv'), avg_hrv) or '无法计算'}")
    lines.append(f"静息心率：{_fmt(d.get('resting_hr'), ' bpm')} vs 均值 {_fmt(avg_rhr, ' bpm')} → {_pct_change(d.get('resting_hr'), avg_rhr) or '无法计算'}")
    lines.append(f"睡眠时长：{_fmt(sleep_total, ' min')} vs 均值 {_fmt(avg_sleep, ' min')} → {_pct_change(sleep_total, avg_sleep) or '无法计算'}")
    lines.append(f"深睡时长：{_fmt(sleep_deep, ' min')} vs 均值 {_fmt(avg_deep, ' min')} → {_pct_change(sleep_deep, avg_deep) or '无法计算'}")
    lines.append(f"压力负荷：{_fmt(d.get('strain'))} vs 均值 {_fmt(avg_strain)} → {_pct_change(d.get('strain'), avg_strain) or '无法计算'}")

    # 异常标记
    anomalies = []
    if d.get("recovery_score") is not None and d["recovery_score"] < 34:
        anomalies.append("恢复分处于红区(<34%)，身体需要休息")
    elif d.get("recovery_score") is not None and d["recovery_score"] < 67:
        anomalies.append("恢复分处于黄区(34-66%)，建议中低强度活动")
    if d.get("hrv") and avg_hrv and d["hrv"] < avg_hrv * 0.8:
        anomalies.append(f"HRV 显著低于基线（{d['hrv']:.1f} vs 均值 {avg_hrv:.1f}），提示身体仍在恢复")
    if d.get("resting_hr") and avg_rhr and d["resting_hr"] > avg_rhr * 1.1:
        anomalies.append(f"静息心率偏高（{d['resting_hr']:.0f} vs 均值 {avg_rhr:.0f}），可能疲劳/脱水")
    if d.get("sleep_efficiency") is not None and d["sleep_efficiency"] < 85:
        anomalies.append(f"睡眠效率偏低（{d['sleep_efficiency']:.1f}%），入睡困难或夜醒频繁")
    if d.get("disturbance_count") is not None and d["disturbance_count"] > 5:
        anomalies.append(f"睡眠干扰次数较多（{d['disturbance_count']:.0f}次），睡眠质量受影响")
    if d.get("spo2") is not None and d["spo2"] < 95:
        anomalies.append(f"血氧偏低（{d['spo2']:.1f}%），关注呼吸状况")

    if anomalies:
        lines.append("")
        lines.append("=== 异常标记（必须在报告中分析）===")
        for a in anomalies:
            lines.append(f"  ⚠️ {a}")
    else:
        lines.append("")
        lines.append("=== 无明显异常，整体状态良好 ===")

    # ── 趋势分析 ──
    recovery_vals = [r.get("recovery_score") for r in reversed(recent_7)]
    hrv_vals = [r.get("hrv") for r in reversed(recent_7)]
    sleep_vals = [r.get("sleep_total_min") for r in reversed(recent_7)]

    lines.append("")
    lines.append("=== 7天趋势方向 ===")
    lines.append(f"恢复分趋势：{_trend_direction(recovery_vals)}")
    lines.append(f"HRV 趋势：{_trend_direction(hrv_vals)}")
    lines.append(f"睡眠趋势：{_trend_direction(sleep_vals)}")

    # 日环比（vs 昨天）
    if len(recent_7) >= 2:
        yesterday = None
        for r in recent_7:
            if r.get("date") != d.get("date") and r.get("recovery_score") is not None:
                yesterday = r
                break
        if yesterday:
            lines.append("")
            lines.append(f"=== 日环比（vs {yesterday['date']}）===")
            lines.append(f"恢复分：{_fmt(d.get('recovery_score'))} vs {_fmt(yesterday.get('recovery_score'))} → {_pct_change(d.get('recovery_score'), yesterday.get('recovery_score')) or '-'}")
            lines.append(f"HRV：{_fmt(d.get('hrv'), ' ms')} vs {_fmt(yesterday.get('hrv'), ' ms')} → {_pct_change(d.get('hrv'), yesterday.get('hrv')) or '-'}")
            lines.append(f"睡眠：{_fmt(sleep_total, ' min')} vs {_fmt(yesterday.get('sleep_total_min'), ' min')} → {_pct_change(sleep_total, yesterday.get('sleep_total_min')) or '-'}")

    # ── 7天明细表格 ──
    lines.append("")
    lines.append("=== 7天明细 ===")
    lines.append("日期 | 恢复分(%) | HRV(ms) | 静息HR | 睡眠(h) | 深睡(min) | 压力分")
    for r in recent_7:
        sleep_h = round(r["sleep_total_min"] / 60, 1) if r.get("sleep_total_min") else None
        lines.append(
            f"{r.get('date', '?')} | "
            f"{_fmt(r.get('recovery_score'))} | "
            f"{_fmt(r.get('hrv'))} | "
            f"{_fmt(r.get('resting_hr'))} | "
            f"{_fmt(sleep_h)} | "
            f"{_fmt(r.get('sleep_deep_min'))} | "
            f"{_fmt(r.get('strain'))}"
        )

    # ── 近期运动记录 ──
    if workouts:
        lines.append("")
        lines.append("=== 近期运动记录 ===")
        for w in workouts:
            sport = w.get("sport_name", "未知")
            w_strain = w.get("strain")
            w_avg_hr = w.get("avg_hr")
            w_max_hr = w.get("max_hr")
            w_dist = w.get("distance_m")
            w_dur = w.get("duration_min")
            detail = f"{w.get('date')} | {sport} | strain {_fmt(w_strain)}"
            if w_avg_hr:
                detail += f" | 平均心率 {w_avg_hr:.0f}"
            if w_max_hr:
                detail += f" | 最高心率 {w_max_hr:.0f}"
            if w_dist and w_dist > 0:
                detail += f" | {w_dist:.0f}m"
            lines.append(f"  {detail}")

    return "\n".join(lines)


# ── 主流程 ───────────────────────────────────────────────────────────────────

def run():
    print("[Daily] Starting daily report...")
    init_db()

    # 1. 拉 WHOOP 数据
    whoop = WhoopClient()
    sync_whoop_data(whoop)

    # 2. 获取最近数据
    recent = get_recent_days(10)
    if not recent:
        print("[Daily] No data found, skipping report")
        return

    today_data = _find_best_today(recent)
    recent_7 = [r for r in recent if r.get("recovery_score") is not None][:7]
    if not recent_7:
        recent_7 = recent[:7]
    print(f"[Daily] Using data from {today_data.get('date')} (recovery: {today_data.get('recovery_score')})")

    # 2.5 获取近期运动记录
    workouts = get_recent_workouts(10)
    print(f"[Daily] Found {len(workouts)} recent workouts")

    # 3. AI 生成晨报
    ai = MinimaxClient()
    prompt = _build_daily_prompt(today_data, recent_7, workouts)
    print(f"[Daily] Prompt length: {len(prompt)} chars")
    print(f"[Daily] Prompt preview:\n{prompt[:500]}...")
    report = ai.chat(DAILY_SYSTEM_PROMPT, prompt, max_tokens=4000)
    print(f"[Daily] Report generated ({len(report)} chars)")

    # 4. 推飞书
    feishu = FeishuClient()
    feishu.send_text(report)
    print("[Daily] Report sent to Feishu")

    # 4.5 生成并发送7天趋势图
    try:
        from src.charts import generate_weekly_chart
        chart_path = generate_weekly_chart(recent)
        if chart_path and chart_path.exists():
            feishu.send_image(chart_path)
            print("[Daily] Chart sent to Feishu")
    except Exception as e:
        print(f"[Daily] Chart generation skipped: {e}")

    # 5. 更新 Excel（仅 git 备份，不推飞书）
    rebuild_excel()

    # 6. Token 轮换
    if whoop.rotated:
        rotate_secrets(whoop.export_secrets())
        print("[Daily] WHOOP token rotated")

    # 7. 标记今日晨报已发（供 bot_poll 兜底检查使用）
    try:
        state_path = config.BOT_STATE_PATH
        state = json.loads(state_path.read_text()) if state_path.exists() and state_path.read_text().strip() else {}
        state["last_report_date"] = datetime.now(config.BEIJING_TZ).strftime("%Y-%m-%d")
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"[Daily] Could not update bot state: {e}")

    print("[Daily] Done!")


if __name__ == "__main__":
    run()
