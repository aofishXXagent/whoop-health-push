# WHOOP Health Push

Personal health data pipeline: automatically sync WHOOP data, generate AI health reports, and push to Feishu (Lark).

## Features

- 🔄 **Auto sync** — Pull recovery, sleep, strain, and workout data from WHOOP API
- 🤖 **AI health reports** — Daily briefings powered by MiniMax AI
- 💬 **Feishu bot** — Push reports and answer health questions via Feishu
- 🔐 **Safe token management** — Handles WHOOP's rotating refresh tokens without breaking
- 📊 **Data export** — SQLite database + Excel + CSV files

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌────────────┐
│   WHOOP API     │────▶│  This Repo   │────▶│  Feishu    │
│  (health data)  │     │  (sync+AI)   │     │  (reports) │
└─────────────────┘     └──────────────┘     └────────────┘
                              │
                        ┌─────┴─────┐
                        │  SQLite   │
                        │  + CSV    │
                        └───────────┘
```

**Runs in two modes:**
- **Local** (recommended): LaunchAgent/cron on your Mac, uses `credentials.json`
- **Cloud**: GitHub Actions on schedule, uses GitHub Secrets

## Quick Start

### 1. Get WHOOP API Credentials

1. Go to [WHOOP Developer Portal](https://developer.whoop.com/)
2. Create an app with redirect URI: `http://localhost:8080/callback`
3. Note your `client_id` and `client_secret`

### 2. Authorize

```bash
# Clone the repo
git clone https://github.com/aofishXXagent/whoop-health-push.git
cd whoop-health-push

# Install dependencies
pip install -r requirements.txt

# Run OAuth flow (opens browser)
python3 scripts/auth_whoop.py
```

This creates `credentials.json` with your tokens.

### 3. Sync Data

```bash
# One-time sync
python3 -m src.export_local

# Or test the token manager
python3 -m src.token_manager
```

### 4. Set Up Auto-Sync (macOS)

```bash
# Create a LaunchAgent for daily sync
cat > ~/Library/LaunchAgents/com.whoop.daily-sync.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.whoop.daily-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>python3</string>
        <string>$(pwd)/src/export_local.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>WHOOP_CRED_PATH</key>
        <string>$(pwd)/credentials.json</string>
    </dict>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.whoop.daily-sync.plist
```

### 5. GitHub Actions (Optional Cloud Backup)

Set these GitHub Secrets:

| Secret | Description |
|--------|-------------|
| `WHOOP_CLIENT_ID` | From WHOOP developer portal |
| `WHOOP_CLIENT_SECRET` | From WHOOP developer portal |
| `WHOOP_ACCESS_TOKEN` | From auth script output |
| `WHOOP_REFRESH_TOKEN` | From auth script output |
| `WHOOP_TOKEN_SAVED_AT` | From auth script output |
| `GH_PAT` | GitHub PAT with `repo` scope (for token rotation) |
| `MINIMAX_API_KEY` | (Optional) For AI reports |
| `FEISHU_APP_ID` | (Optional) For Feishu bot |
| `FEISHU_APP_SECRET` | (Optional) For Feishu bot |
| `FEISHU_CHAT_ID` | (Optional) For Feishu bot |
| `FEISHU_BOT_OPEN_ID` | (Optional) For Feishu bot |

## Token Management

WHOOP uses **rotating refresh tokens** — each refresh token can only be used once. This is the most common source of issues.

### How `token_manager.py` Protects You

```
Request → Is access token valid?
           ├── YES → Use it directly (no refresh consumed!)
           └── NO (401) → Backup old creds
                          → Refresh token
                          → Atomic save new tokens
                          → Use new access token
```

**Key principles:**
1. **Never refresh preemptively** — only when you get a 401
2. **Atomic saves** — write to `.tmp` file, then `os.replace()` (no partial writes)
3. **Backup before refresh** — `credentials.json.backup` always has the last known good state
4. **One refresh token consumer** — don't run multiple instances that might both try to refresh

### If Tokens Break

If you see `"Token refresh failed"`:
```bash
# Re-authorize (takes 30 seconds)
python3 scripts/auth_whoop.py
```

## Project Structure

```
├── src/
│   ├── token_manager.py   # Safe WHOOP token handling (core)
│   ├── whoop_client.py     # WHOOP API client
│   ├── config.py           # Configuration (env vars + paths)
│   ├── database.py         # SQLite operations
│   ├── bot_poll.py         # Feishu bot message handler
│   ├── report_daily.py     # AI daily health report
│   ├── feishu_client.py    # Feishu API client
│   ├── minimax_client.py   # MiniMax AI client
│   ├── charts.py           # Data visualization
│   ├── excel_manager.py    # Excel export
│   └── github_secrets.py   # GitHub Secrets rotation
├── scripts/
│   └── auth_whoop.py       # OAuth authorization helper
├── data/
│   ├── whoop_data.db       # SQLite database
│   ├── whoop_health.xlsx   # Excel export
│   └── bot_state.json      # Bot state tracking
├── credentials.example.json # Template for credentials
└── .github/workflows/
    ├── bot-poll.yml         # Scheduled bot + sync
    └── daily-report.yml     # Daily health report
```

## API Rate Limits

WHOOP API limits:
- **100 requests/minute**
- **10,000 requests/day**

Typical usage with this setup: ~1,500 requests/day (15% of daily limit).

## License

MIT
