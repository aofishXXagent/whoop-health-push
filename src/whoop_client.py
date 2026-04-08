"""WHOOP API Client — safe token management with automatic refresh.

Uses token_manager for credential handling:
- Only refreshes when access token is actually expired (401)
- Atomically saves new tokens to prevent corruption
- Backs up credentials before any refresh
"""

import requests
from datetime import datetime, timezone
from src.token_manager import get_valid_token, fetch_paginated, API_BASE


class WhoopClient:
    API_BASE = API_BASE

    def __init__(self):
        creds, self.access_token = get_valid_token()
        self.client_id = creds["client_id"]
        self.client_secret = creds["client_secret"]
        self.refresh_token = creds["refresh_token"]
        self.rotated = self.access_token != creds.get("_original_access_token", self.access_token)

    def export_secrets(self) -> dict:
        """Return secrets dict for GitHub Secrets rotation."""
        return {
            "WHOOP_ACCESS_TOKEN": self.access_token,
            "WHOOP_REFRESH_TOKEN": self.refresh_token,
            "WHOOP_TOKEN_SAVED_AT": datetime.now(timezone.utc).isoformat(),
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
        if resp.status_code == 401:
            # Re-authenticate via token manager
            _, self.access_token = get_valid_token()
            resp = requests.get(
                f"{self.API_BASE}{path}",
                headers=self._headers(),
                params=params or {},
                timeout=15,
            )
        resp.raise_for_status()
        return resp.json()

    def _fetch_paginated(self, path: str, max_records: int = 25) -> list:
        """Paginated fetch using token manager for resilience."""
        return fetch_paginated(path.lstrip("/"), headers=self._headers(), max_records=max_records)

    # ── Business methods ────────────────────────────────────────────────────

    def fetch_recoveries(self, limit: int = 10) -> list:
        return self._fetch_paginated("/recovery", max_records=limit)

    def fetch_sleeps(self, limit: int = 10) -> list:
        return self._fetch_paginated("/activity/sleep", max_records=limit)

    def fetch_cycles(self, limit: int = 10) -> list:
        return self._fetch_paginated("/cycle", max_records=limit)

    def fetch_workouts(self, limit: int = 50) -> list:
        return self._fetch_paginated("/activity/workout", max_records=limit)
