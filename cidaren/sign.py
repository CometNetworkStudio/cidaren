"""词达人请求签名。

协议事实：sign = md5(按请求实际使用的键值对顺序以 '&' 连接 + SALT)。
注意是**保持插入顺序**，不是字典序排序。
"""

from __future__ import annotations

import hashlib

SALT = "ajfajfamsnfaflfasakljdlalkflak"


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def build_sign(params) -> str:
    """:param params: dict（插入序）或 [(k, v), ...]。"""
    items = params.items() if isinstance(params, dict) else params
    payload = "&".join(f"{key}={value}" for key, value in items) + SALT
    return md5_hex(payload)


def signed(params: dict) -> dict:
    """返回在原 dict 上追加 sign（不修改原对象）。"""
    body = dict(params)
    body["sign"] = build_sign(params)
    return body
