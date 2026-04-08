"""飞书机器人轮询：检查新消息 → AI 回复 → 更新状态。每次运行也兜底检查今日晨报是否已发。"""

import json
from pathlib import Path
from src import config
from src.database import init_db, get_recent_days
from src.feishu_client import FeishuClient
from src.minimax_client import MinimaxClient
from datetime import datetime
from src.config import BEIJING_TZ

# 晨报触发时间：北京时间 08:00
REPORT_HOUR_BEIJING = 8


BOT_SYSTEM_PROMPT = """你是用户的私人健康教练。用户戴着 WHOOP 手环，每周跑步 2-3 次，对数据是新手。

你持有用户最近 7 天的真实健康数据。用户会问三类问题：
- 运动决策（"今天能跑步吗？""这周练了多少？"）
- 身体状态（"我最近状态怎么样？""为什么今天觉得累？"）
- 睡眠诊断（"昨晚睡得怎么样？""我该几点睡？"）

回答规则：
1. 必须引用数据中的具体数值（如"你的 HRV 64ms，比 7 天均值高 4%"）
2. 建议要具体可执行（如"轻松跑 30 分钟，心率控制在 130 以下"），不说"适当运动"
3. 遇到专业术语用一句话解释（如"HRV 就是心跳间隔的变化，越高说明身体越放松"）
4. 不过度解读正常波动，不吓人
5. 数据没有的内容诚实说"这个 WHOOP 没法测"
6. 语气简洁专业，不啰嗦
7. 回复 200 字以内
"""


def _load_state() -> dict:
    if config.BOT_STATE_PATH.exists():
        text = config.BOT_STATE_PATH.read_text().strip()
        if text:
            return json.loads(text)
    return {}


def _save_state(state: dict):
    config.BOT_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _build_whoop_context(recent: list) -> str:
    """构建7天健康数据上下文，包含预计算洞察。"""
    if not recent:
        return "暂无健康数据"

    # 找最新有效数据日
    latest = recent[0]
    for r in recent:
        if r.get("recovery_score") is not None and r.get("sleep_total_min") is not None:
            latest = r
            break

    def fmt(v, unit=""):
        if v is None:
            return "暂无"
        if isinstance(v, float):
            return f"{v:.1f}{unit}"
        return f"{v}{unit}"

    def avg(key):
        vals = [r[key] for r in recent if r.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    lines = []
    lines.append(f"=== 最新数据（{latest.get('date', '未知')}）===")
    lines.append(f"恢复分：{fmt(latest.get('recovery_score'), '%')}")
    lines.append(f"HRV：{fmt(latest.get('hrv'), ' ms')}（7天均值：{fmt(avg('hrv'), ' ms')}）")
    lines.append(f"静息心率：{fmt(latest.get('resting_hr'), ' bpm')}（7天均值：{fmt(avg('resting_hr'), ' bpm')}）")
    lines.append(f"血氧：{fmt(latest.get('spo2'), '%')}")
    lines.append(f"皮肤温度：{fmt(latest.get('skin_temp'), ' °C')}")

    sleep_total = latest.get("sleep_total_min")
    sleep_deep = latest.get("sleep_deep_min")
    sleep_rem = latest.get("sleep_rem_min")
    lines.append(f"睡眠：{fmt(round(sleep_total/60, 1) if sleep_total else None, ' h')}（深睡 {fmt(sleep_deep, ' min')}，REM {fmt(sleep_rem, ' min')}）")
    lines.append(f"睡眠效率：{fmt(latest.get('sleep_efficiency'), '%')}  一致性：{fmt(latest.get('sleep_consistency'), '%')}")
    lines.append(f"干扰次数：{fmt(latest.get('disturbance_count'))}  呼吸频率：{fmt(latest.get('respiratory_rate'), ' 次/min')}")
    lines.append(f"压力分(Strain)：{fmt(latest.get('strain'))}  能量消耗：{fmt(latest.get('kilojoules'), ' kJ')}")

    # 睡眠占比
    if sleep_total and sleep_total > 0:
        if sleep_deep:
            lines.append(f"深睡占比：{sleep_deep/sleep_total*100:.1f}%（理想15-20%）")
        if sleep_rem:
            lines.append(f"REM占比：{sleep_rem/sleep_total*100:.1f}%（理想20-25%）")

    # 恢复区间
    rs = latest.get("recovery_score")
    if rs is not None:
        zone = "绿区(恢复充分)" if rs >= 67 else ("黄区(部分恢复)" if rs >= 34 else "红区(需休息)")
        lines.append(f"恢复状态：{zone}")

    # 7天趋势
    lines.append(f"\n=== 7天趋势 ===")
    lines.append(f"7天均值 — 恢复：{fmt(avg('recovery_score'), '%')} | HRV：{fmt(avg('hrv'), ' ms')} | 睡眠：{fmt(round(avg('sleep_total_min')/60, 1) if avg('sleep_total_min') else None, ' h')}")

    lines.append("日期 | 恢复 | HRV | 睡眠(h)")
    for r in recent[:7]:
        sleep_h = round(r["sleep_total_min"]/60, 1) if r.get("sleep_total_min") else None
        lines.append(f"{r.get('date','?')} | {fmt(r.get('recovery_score'))}% | {fmt(r.get('hrv'))} | {fmt(sleep_h)}h")

    return "\n".join(lines)


def _extract_text(msg: dict):
    """从飞书消息中提取文本内容。"""
    msg_type = msg.get("msg_type", "")
    body = msg.get("body", {})
    content_str = body.get("content", "{}")

    try:
        content = json.loads(content_str)
    except (json.JSONDecodeError, TypeError):
        return None

    if msg_type == "text":
        return content.get("text", "").strip()
    elif msg_type == "post":
        # 富文本消息，拼接所有文本
        texts = []
        for lang in content.values():
            if isinstance(lang, dict) and "content" in lang:
                for line in lang["content"]:
                    for elem in line:
                        if elem.get("tag") == "text":
                            texts.append(elem.get("text", ""))
        return " ".join(texts).strip() if texts else None

    return None


def _maybe_send_daily_report(state: dict):
    """若今日晨报未发且已过北京时间 08:00，立即补发。"""
    now = datetime.now(BEIJING_TZ)
    today_str = now.strftime("%Y-%m-%d")
    last_report_date = state.get("last_report_date", "")

    if last_report_date == today_str:
        return  # 今天已发

    if now.hour < REPORT_HOUR_BEIJING:
        return  # 还没到时间

    print(f"[Bot] Daily report not sent for {today_str}, triggering now...")
    try:
        import src.report_daily as rd
        rd.run()
        state["last_report_date"] = today_str
        print("[Bot] Daily report sent successfully")
    except Exception as e:
        print(f"[Bot] Daily report failed: {e}")


def run():
    print("[Bot] Starting poll...")
    init_db()

    state = _load_state()

    # ── 兜底晨报（独立于消息轮询，确保即使飞书读取失败也能发报告）──
    _maybe_send_daily_report(state)

    # ── 消息轮询 ──
    try:
        feishu = FeishuClient()
        last_id = state.get("last_message_id")
        messages = feishu.list_messages()
    except Exception as e:
        print(f"[Bot] Feishu list_messages failed: {e}")
        print("[Bot] Skipping message poll, saving state")
        state["last_check_ts"] = datetime.now(BEIJING_TZ).isoformat()
        state["last_error"] = f"list_messages: {e}"
        _save_state(state)
        return

    # 找出 last_id 之后的新消息
    new_msgs = []
    for msg in messages:
        msg_id = msg.get("message_id", "")
        if msg_id == last_id:
            break
        # 跳过机器人自己的消息
        sender = msg.get("sender", {})
        if sender.get("id") == config.FEISHU_BOT_OPEN_ID:
            continue
        if sender.get("sender_type") == "app":
            continue
        # 只处理文本和富文本
        if msg.get("msg_type") not in ("text", "post"):
            continue
        new_msgs.append(msg)

    new_msgs.reverse()  # 按时间从旧到新处理

    if not new_msgs and last_id is None:
        # 首次运行，记录最新消息 ID，发一条就绪消息
        if messages:
            state["last_message_id"] = messages[0].get("message_id", "")
        try:
            feishu.send_text("🤖 健康助手已就绪！有什么健康问题随时问我～")
        except Exception as e:
            print(f"[Bot] Failed to send ready message: {e}")
        _save_state(state)
        print("[Bot] First run, sent ready message")
        return

    if not new_msgs:
        state["last_check_ts"] = datetime.now(BEIJING_TZ).isoformat()
        _save_state(state)
        print("[Bot] No new messages")
        return

    # 加载 Whoop 数据上下文
    recent = get_recent_days(7)
    whoop_ctx = _build_whoop_context(recent)
    ai = MinimaxClient()

    for msg in new_msgs:
        user_text = _extract_text(msg)
        if not user_text:
            continue

        prompt = f"用户的 Whoop 健康数据：\n{whoop_ctx}\n\n用户说：{user_text}"
        reply = ai.chat(BOT_SYSTEM_PROMPT, prompt, max_tokens=600)
        try:
            feishu.send_text(reply)
        except Exception as e:
            print(f"[Bot] Failed to send reply: {e}")
        print(f"[Bot] Replied to: {user_text[:30]}...")

        state["last_message_id"] = msg.get("message_id", "")

    state["last_check_ts"] = datetime.now(BEIJING_TZ).isoformat()
    _save_state(state)
    print(f"[Bot] Processed {len(new_msgs)} messages")


if __name__ == "__main__":
    run()
