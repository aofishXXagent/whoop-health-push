"""MiniMax M2.7 聊天补全客户端。"""

import requests
from src import config


class MinimaxClient:
    def __init__(self):
        self.api_key = config.MINIMAX_API_KEY
        self.model = config.MINIMAX_MODEL
        self.url = config.MINIMAX_API_URL

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> str:
        """调用 MiniMax 生成文本，返回内容字符串。"""
        resp = requests.post(
            self.url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        # MiniMax 可能返回 HTTP 200 但 body 含错误
        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            raise RuntimeError(
                f"MiniMax error: {base_resp.get('status_msg', 'unknown')}"
            )

        return data["choices"][0]["message"]["content"]
