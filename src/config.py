"""Unified config — reads from environment variables (GitHub Actions)
or falls back to credentials.json (local use)."""

import os
from pathlib import Path
from datetime import timezone, timedelta

# ── Timezone ─────────────────────────────────────────────────────────────────
BEIJING_TZ = timezone(timedelta(hours=8))

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "whoop_data.db"
EXCEL_PATH = DATA_DIR / "whoop_health.xlsx"
BOT_STATE_PATH = DATA_DIR / "bot_state.json"
CRED_PATH = REPO_ROOT / "credentials.json"


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return val


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ── WHOOP (env vars for GitHub Actions; local uses token_manager) ────────────
WHOOP_CLIENT_ID = _optional("WHOOP_CLIENT_ID")
WHOOP_CLIENT_SECRET = _optional("WHOOP_CLIENT_SECRET")
WHOOP_ACCESS_TOKEN = _optional("WHOOP_ACCESS_TOKEN")
WHOOP_REFRESH_TOKEN = _optional("WHOOP_REFRESH_TOKEN")
WHOOP_TOKEN_SAVED_AT = _optional("WHOOP_TOKEN_SAVED_AT")

# ── MiniMax ──────────────────────────────────────────────────────────────────
MINIMAX_API_KEY = _optional("MINIMAX_API_KEY")
MINIMAX_MODEL = "MiniMax-M2.7"
MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"

# ── Feishu ───────────────────────────────────────────────────────────────────
FEISHU_APP_ID = _optional("FEISHU_APP_ID")
FEISHU_APP_SECRET = _optional("FEISHU_APP_SECRET")
FEISHU_CHAT_ID = _optional("FEISHU_CHAT_ID")
FEISHU_BOT_OPEN_ID = _optional("FEISHU_BOT_OPEN_ID")

# ── GitHub (token rotation) ─────────────────────────────────────────────────
GH_PAT = _optional("GH_PAT")
GH_REPO = _optional("GITHUB_REPOSITORY")
