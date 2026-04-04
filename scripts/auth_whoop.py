#!/usr/bin/env python3
"""一次性本地运行：完成 WHOOP OAuth 授权，输出 3 个 GitHub Secret 值。"""

import http.server
import json
import urllib.parse
import webbrowser
from datetime import datetime, timezone

import requests

# ── 配置（仅本地使用）─────────────────────────────────────────────────────────
CLIENT_ID = input("请输入 WHOOP_CLIENT_ID: ").strip()
CLIENT_SECRET = input("请输入 WHOOP_CLIENT_SECRET: ").strip()
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = "offline read:recovery read:cycles read:sleep read:workout read:profile read:body_measurement"

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"


def main():
    # 1. 打开浏览器授权
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": "whoop_auth",
    }
    auth_link = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    print(f"\n正在打开浏览器进行 WHOOP 授权...\n{auth_link}\n")
    webbrowser.open(auth_link)

    # 2. 本地 HTTP 服务器接收回调
    auth_code = None

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            auth_code = params.get("code", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("✅ 授权成功！可以关闭此页面。".encode("utf-8"))

        def log_message(self, *args):
            pass  # 静默日志

    server = http.server.HTTPServer(("localhost", 8080), Handler)
    print("等待 WHOOP 授权回调...")
    server.handle_request()

    if not auth_code:
        print("❌ 未收到授权码")
        return

    # 3. 用授权码换 token
    print("正在获取 token...")
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token_data = resp.json()

    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]
    saved_at = datetime.now(timezone.utc).isoformat()

    # 4. 输出结果
    print("\n" + "=" * 60)
    print("✅ WHOOP OAuth 授权成功！")
    print("请将以下值配置到 GitHub Secrets：")
    print("=" * 60)
    print(f"\nWHOOP_ACCESS_TOKEN={access_token}")
    print(f"\nWHOOP_REFRESH_TOKEN={refresh_token}")
    print(f"\nWHOOP_TOKEN_SAVED_AT={saved_at}")
    print(f"\nWHOOP_CLIENT_ID={CLIENT_ID}")
    print(f"\nWHOOP_CLIENT_SECRET={CLIENT_SECRET}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
