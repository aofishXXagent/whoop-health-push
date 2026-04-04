"""WHOOP API 客户端：OAuth token 管理 + REST 数据拉取。"""

import requests
from datetime import datetime, timedelta, timezone
from src import config


class WhoopClient:
    TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
    API_BASE = "https://api.prod.whoop.com/developer/v2"

    def __init__(self):
        self.client_id = config.WHOOP_CLIENT_ID
        self.client_secret = config.WHOOP_CLIENT_SECRET
        self.access_token = config.WHOOP_ACCESS_TOKEN
        self.refresh_token = config.WHOOP_REFRESH_TOKEN
        self.saved_at = datetime.fromisoformat(config.WHOOP_TOKEN_SAVED_AT)
        self.rotated = False
        self._maybe_refresh()

    def _maybe_refresh(self):
        age = (datetime.now(timezone.utc) - self.saved_at).total_seconds()
        if age > 3000:  # 50 分钟，保守缓冲
            self._do_refresh()

    def _do_refresh(self):
        resp = requests.post(
            self.TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.saved_at = datetime.now(timezone.utc)
        self.rotated = True

    def export_secrets(self) -> dict:
        """返回需要更新到 GitHub Secrets 的键值对。"""
        return {
            "WHOOP_ACCESS_TOKEN": self.access_token,
            "WHOOP_REFRESH_TOKEN": self.refresh_token,
            "WHOOP_TOKEN_SAVED_AT": self.saved_at.isoformat(),
        }

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _get(self, path: str, params=None) -> dict:
        resp = requests.get(
            f"{self.API_BASE}{path}",
            headers=self._headers(),
            params=params or {},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _fetch_paginated(self, path: str, max_records: int = 25) -> list:
        """分页拉取数据。"""
        records = []
        next_token = None
        while len(records) < max_records:
            params = {"limit": min(25, max_records - len(records))}
            if next_token:
                params["nextToken"] = next_token
            data = self._get(path, params)
            records.extend(data.get("records", []))
            next_token = data.get("next_token")
            if not next_token:
                break
        return records

    # ── 业务方法 ─────────────────────────────────────────────────────────────

    def fetch_recoveries(self, limit: int = 10) -> list:
        return self._fetch_paginated("/recovery", max_records=limit)

    def fetch_sleeps(self, limit: int = 10) -> list:
        return self._fetch_paginated("/activity/sleep", max_records=limit)

    def fetch_cycles(self, limit: int = 10) -> list:
        return self._fetch_paginated("/cycle", max_records=limit)

    def fetch_workouts(self, limit: int = 50) -> list:
        return self._fetch_paginated("/activity/workout", max_records=limit)
