"""配置读取：仅环境变量（可选从仓库根 .env 载入，不覆盖已有变量）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"


def load_dotenv(path: Path = DEFAULT_ENV_FILE, env: dict | None = None) -> dict:
    """把 KEY=VALUE 行读入 env，已存在的键不覆盖。返回被写入的键。"""
    target = os.environ if env is None else env
    if not path.is_file():
        return target
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in target:
            target[key] = value
    return target


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


@dataclass(frozen=True)
class Config:
    llm: LLMConfig
    agent_port: int
    bank_mode: str
    bank_addr: str
    bank_local_path: str
    http_timeout: float
    http_retries: int
    http_proxy: str
    platform_concurrency: int
    request_min_interval: float
    request_max_interval: float

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Config":
        # 显式传入 env 时直接使用（便于测试隔离）；否则从进程环境 + 仓库根 .env 读取。
        e = load_dotenv() if env is None else env
        get = e.get
        return cls(
            llm=LLMConfig(
                base_url=(get("OMNITASK_LLM_BASE_URL") or "").rstrip("/"),
                api_key=get("OMNITASK_LLM_API_KEY") or "",
                model=get("OMNITASK_LLM_MODEL") or "",
            ),
            agent_port=int(get("OMNITASK_AGENT_PORT") or 50051),
            bank_mode=(get("OMNITASK_BANK_MODE") or "local").lower(),
            bank_addr=get("OMNITASK_BANK_ADDR") or "127.0.0.1:9000",
            bank_local_path=get("OMNITASK_BANK_LOCAL_PATH")
            or str(Path(__file__).resolve().parents[1] / ".cache" / "bank.sqlite3"),
            http_timeout=float(get("OMNITASK_HTTP_TIMEOUT") or 20.0),
            http_retries=int(get("OMNITASK_HTTP_RETRIES") or 3),
            http_proxy=get("OMNITASK_HTTP_PROXY") or "",
            platform_concurrency=int(get("OMNITASK_PLATFORM_CONCURRENCY") or 2),
            request_min_interval=float(get("OMNITASK_REQUEST_MIN_INTERVAL") or 0.8),
            request_max_interval=float(get("OMNITASK_REQUEST_MAX_INTERVAL") or 2.5),
        )
