"""统一配置入口，所有环境变量在此读取。"""

import os
from pathlib import Path
from datetime import timezone, timedelta

# ── 时区 ─────────────────────────────────────────────────────────────────────
BEIJING_TZ = timezone(timedelta(hours=8))

# ── 路径 ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "whoop_data.db"
EXCEL_PATH = DATA_DIR / "whoop_health.xlsx"
BOT_STATE_PATH = DATA_DIR / "bot_state.json"


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return val


# ── WHOOP ────────────────────────────────────────────────────────────────────
WHOOP_CLIENT_ID = _require("WHOOP_CLIENT_ID")
WHOOP_CLIENT_SECRET = _require("WHOOP_CLIENT_SECRET")
WHOOP_ACCESS_TOKEN = _require("WHOOP_ACCESS_TOKEN")
WHOOP_REFRESH_TOKEN = _require("WHOOP_REFRESH_TOKEN")
WHOOP_TOKEN_SAVED_AT = _require("WHOOP_TOKEN_SAVED_AT")

# ── MiniMax ──────────────────────────────────────────────────────────────────
MINIMAX_API_KEY = _require("MINIMAX_API_KEY")
MINIMAX_MODEL = "MiniMax-M2.7"
MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"

# ── 飞书 ─────────────────────────────────────────────────────────────────────
FEISHU_APP_ID = _require("FEISHU_APP_ID")
FEISHU_APP_SECRET = _require("FEISHU_APP_SECRET")
FEISHU_CHAT_ID = _require("FEISHU_CHAT_ID")
FEISHU_BOT_OPEN_ID = _require("FEISHU_BOT_OPEN_ID")

# ── GitHub（token 轮换用）────────────────────────────────────────────────────
GH_PAT = os.environ.get("GH_PAT", "")
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "")
