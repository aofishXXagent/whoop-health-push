"""飞书客户端：消息发送、消息拉取、Drive 文件上传。"""

import hashlib
import json
import time
from pathlib import Path

import requests
from src import config


class FeishuClient:
    BASE = "https://open.feishu.cn/open-apis"

    def __init__(self):
        self._token = None
        self._token_expires_at: float = 0

    def _tenant_token(self) -> str:
        if self._token and time.time() < self._token_expires_at:
            return self._token
        resp = requests.post(
            f"{self.BASE}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": config.FEISHU_APP_ID,
                "app_secret": config.FEISHU_APP_SECRET,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["tenant_access_token"]
        self._token_expires_at = time.time() + data.get("expire", 7200) - 60
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._tenant_token()}",
            "Content-Type": "application/json",
        }

    # ── 消息 ─────────────────────────────────────────────────────────────────

    def send_text(self, text: str, chat_id=None) -> dict:
        """发送文本消息到群聊。"""
        chat_id = chat_id or config.FEISHU_CHAT_ID
        resp = requests.post(
            f"{self.BASE}/im/v1/messages?receive_id_type=chat_id",
            headers=self._headers(),
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def list_messages(
        self, chat_id=None, page_size: int = 20
    ) -> list:
        """拉取群聊最近消息（最新在前）。"""
        chat_id = chat_id or config.FEISHU_CHAT_ID
        resp = requests.get(
            f"{self.BASE}/im/v1/messages",
            headers=self._headers(),
            params={
                "container_id_type": "chat",
                "container_id": chat_id,
                "sort_type": "ByCreateTimeDesc",
                "page_size": page_size,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("items", [])

    def send_image(self, image_path: Path, chat_id=None) -> dict:
        """上传图片并发送到群聊。"""
        chat_id = chat_id or config.FEISHU_CHAT_ID
        token = self._tenant_token()

        # 上传图片获取 image_key
        upload_resp = requests.post(
            f"{self.BASE}/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            data={"image_type": "message"},
            files={"image": open(image_path, "rb")},
            timeout=30,
        )
        upload_resp.raise_for_status()
        image_key = upload_resp.json().get("data", {}).get("image_key")
        if not image_key:
            print(f"[Feishu] Image upload failed: {upload_resp.json()}")
            return {}

        # 发送图片消息
        resp = requests.post(
            f"{self.BASE}/im/v1/messages?receive_id_type=chat_id",
            headers=self._headers(),
            json={
                "receive_id": chat_id,
                "msg_type": "image",
                "content": json.dumps({"image_key": image_key}),
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Drive 上传 ───────────────────────────────────────────────────────────

    def upload_file(self, file_path: Path, file_name: str):
        """上传文件到飞书云文档，返回 file_token。

        使用单次上传 API（适合 < 20MB 的文件）。
        """
        token = self._tenant_token()
        size = file_path.stat().st_size

        resp = requests.post(
            f"{self.BASE}/drive/v1/files/upload_all",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "file_name": file_name,
                "parent_type": "explorer",
                "parent_node": "",
                "size": str(size),
            },
            files={"file": (file_name, open(file_path, "rb"))},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            print(f"[Feishu Drive] upload failed: {data.get('msg')}")
            return None
        return data.get("data", {}).get("file_token")
