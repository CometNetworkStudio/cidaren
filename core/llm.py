"""OpenAI 兼容的 LLM 客户端（词达人答题兜底，仅在三处策略都未命中时使用）。"""

from __future__ import annotations

import requests

from .config import LLMConfig


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self, config: LLMConfig, timeout: float = 30.0) -> None:
        self.config = config
        self.timeout = timeout

    def complete(self, prompt: str, system: str | None = None, temperature: float = 0.0) -> str:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, temperature=temperature)

    def chat(self, messages: list[dict], temperature: float = 0.0) -> str:
        if not self.config.enabled:
            raise LLMUnavailable("LLM 未配置（需要 base_url/api_key/model）")
        resp = requests.post(
            f"{self.config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "messages": messages,
                "temperature": temperature,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
