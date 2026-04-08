"""
Safe WHOOP Token Manager

WHOOP uses rotating refresh tokens — each refresh token is single-use.
If you refresh and fail to save the new tokens, the old refresh token
is already invalidated and you'll need to re-authorize via OAuth.

This module protects against that by:
1. Only refreshing when the access token is actually expired (401)
2. Atomically saving new tokens (write to tmp file, then rename)
3. Backing up old credentials before any refresh
4. Re-authenticating mid-request if tokens expire during a long fetch
"""

import json
import os
import shutil
import requests
from datetime import datetime, timezone

TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
API_BASE = "https://api.prod.whoop.com/developer/v2"

# Default credential path — override with WHOOP_CRED_PATH env var
_DEFAULT_CRED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "credentials.json"
)
CRED_PATH = os.environ.get("WHOOP_CRED_PATH", _DEFAULT_CRED_PATH)


def load_credentials(path=None):
    """Load credentials from JSON file."""
    with open(path or CRED_PATH) as f:
        return json.load(f)


def _atomic_save(creds, path=None):
    """Atomic save: write to .tmp then rename (prevents partial writes)."""
    target = path or CRED_PATH
    tmp_path = target + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(creds, f, indent=2)
    os.replace(tmp_path, target)


def _backup_credentials(path=None):
    """Backup current credentials before refresh."""
    target = path or CRED_PATH
    if os.path.exists(target):
        shutil.copy2(target, target + ".backup")


def _test_access_token(access_token):
    """Quick check if access token is still valid."""
    try:
        resp = requests.get(
            f"{API_BASE}/user/profile/basic",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def get_valid_token(cred_path=None):
    """
    Get a valid access token, refreshing only if necessary.

    Returns:
        tuple: (creds_dict, access_token_string)

    Raises:
        RuntimeError: If refresh fails (likely needs re-authorization)

    Flow:
        1. Load credentials
        2. Test access token with a lightweight API call
        3. If valid → return immediately (no refresh token consumed!)
        4. If expired → refresh using refresh token
        5. Save new tokens atomically → return
    """
    creds = load_credentials(cred_path)

    # Try current access token first — avoids unnecessary refresh
    if _test_access_token(creds["access_token"]):
        return creds, creds["access_token"]

    # Access token expired, must refresh
    print("[TokenManager] Access token expired, refreshing...")
    _backup_credentials(cred_path)

    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": creds["refresh_token"],
                "client_id": creds["client_id"],
                "client_secret": creds["client_secret"],
            },
            timeout=30,
        )
    except Exception as e:
        raise RuntimeError(f"Token refresh network error: {e}") from e

    if resp.status_code != 200:
        raise RuntimeError(
            f"Token refresh failed ({resp.status_code}): {resp.text[:300]}\n"
            "The refresh token may be expired. Re-run: python3 scripts/auth_whoop.py"
        )

    tokens = resp.json()
    creds["access_token"] = tokens["access_token"]
    if "refresh_token" in tokens:
        creds["refresh_token"] = tokens["refresh_token"]

    _atomic_save(creds, cred_path)
    print(f"[TokenManager] Refreshed at {datetime.now(timezone.utc).isoformat()}")

    return creds, creds["access_token"]


def get_headers(cred_path=None):
    """Get Authorization headers with a valid token."""
    _, token = get_valid_token(cred_path)
    return {"Authorization": f"Bearer {token}"}


def fetch_paginated(endpoint, headers=None, max_records=25, cred_path=None):
    """
    Fetch records from a paginated WHOOP API endpoint.

    Handles mid-fetch token expiry by re-authenticating automatically.
    """
    if headers is None:
        headers = get_headers(cred_path)

    records = []
    next_token = None

    while len(records) < max_records:
        params = {"limit": min(25, max_records - len(records))}
        if next_token:
            params["nextToken"] = next_token

        resp = requests.get(
            f"{API_BASE}/{endpoint}",
            headers=headers,
            params=params,
            timeout=15,
        )

        if resp.status_code == 401:
            # Token expired during fetch — re-authenticate and retry
            print("[TokenManager] Got 401 during fetch, re-authenticating...")
            _, new_token = get_valid_token(cred_path)
            headers = {"Authorization": f"Bearer {new_token}"}
            resp = requests.get(
                f"{API_BASE}/{endpoint}",
                headers=headers,
                params=params,
                timeout=15,
            )

        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        next_token = data.get("next_token")
        if not next_token:
            break

    return records


if __name__ == "__main__":
    try:
        creds, token = get_valid_token()
        print(f"✅ Token valid (access: {token[:15]}...)")
        print(f"   Credentials: {CRED_PATH}")
    except Exception as e:
        print(f"❌ {e}")
