"""词达人响应解混淆（jv）与 base64 解码。

协议事实（自参考实现提取，独立重写）：
- 正常响应 data 为 base64；被混淆时 base64 解码会失败。
- jv 以 "2_"/"3_" 开头，对应两张已知规则表；未知 jv 退回默认 2_9214。
- 2_x：按索引删除噪声字符。
- 3_x：先按 uc 段删除，再按 avg 分块、loc 重排。
- 解出后正则取首个 `{"...` 作为 JSON。
"""

from __future__ import annotations

import base64
import json
import re

JV_TWO = {
    "2_1254": [0, 1, 2, 4, 5, 36, 47, 48, 59, 96, 107],
    "2_9214": [0, 1, 2, 4, 5, 6, 7, 48, 49, 66, 149, 150, 284, 374, 375],
    "2_10232": [0, 1, 2, 5, 6, 7, 8, 46, 65, 66, 199, 270, 328, 329],
    "2_10234": [0, 1, 2, 4, 5, 6, 7, 46, 65, 66, 198, 270, 328, 329],
}

JV_THREE = {
    "3_1021": {
        "uc": [{"s": 0, "n": 1}, {"s": 1, "n": 2}, {"s": 33, "n": 1}, {"s": 57, "n": 1}, {"s": 111, "n": 1}],
        "avg": 5,
        "loc": [1, 3, 2, 0, 4],
    },
    "3_2265": {
        "uc": [{"s": 0, "n": 2}, {"s": 1, "n": 3}, {"s": 33, "n": 1}, {"s": 57, "n": 1}, {"s": 121, "n": 1}],
        "avg": 5,
        "loc": [3, 1, 0, 4, 2],
    },
    "3_2277": {
        "uc": [{"s": 0, "n": 3}, {"s": 1, "n": 3}, {"s": 32, "n": 2}, {"s": 50, "n": 1}, {"s": 110, "n": 1}],
        "avg": 5,
        "loc": [3, 1, 0, 4, 2],
    },
}

DEFAULT_JV_TWO = JV_TWO["2_9214"]


class UnknownJv(RuntimeError):
    """jv 不在已知集合：应保留样本并上报，而非用默认规则硬解。"""


class DecodeError(RuntimeError):
    pass


def is_known_jv(jv: str) -> bool:
    jv = str(jv or "")
    return jv in ("", "0") or jv in JV_TWO or jv in JV_THREE


def strip_noise(data: str, rules) -> str:
    if not rules:
        return data
    if isinstance(rules[0], int):
        chars = list(data)
        for index in sorted(rules, reverse=True):
            if 0 <= index < len(chars):
                del chars[index]
        return "".join(chars)
    for rule in rules:
        start, count = rule["s"], rule["n"]
        data = (data[:start] if start else "") + data[start + count :]
    return data


def _deobfuscate(data: str, jv: str) -> str:
    jv = str(jv or "")
    if jv.startswith("3_") and jv in JV_THREE:
        cfg = JV_THREE[jv]
        cleaned = strip_noise(data, cfg["uc"])
        avg = cfg["avg"]
        chunk = len(cleaned) // avg
        if chunk <= 0:
            return cleaned
        pieces = [cleaned[i * chunk : (i + 1) * chunk] for i in range(avg)]
        out = "".join(pieces[cfg["loc"].index(i)] for i in range(avg))
        remainder = len(cleaned) - avg * chunk
        if remainder:
            out += cleaned[avg * chunk :]
        return out
    if jv.startswith("2_") and jv in JV_TWO:
        return strip_noise(data, JV_TWO[jv])
    if jv.startswith("2_") or jv.startswith("3_"):
        raise UnknownJv(f"unknown jv: {jv}")
    return strip_noise(data, DEFAULT_JV_TWO)


def _extract_json(text: str) -> dict:
    match = re.findall(r'\{"[\s\S]*', text)
    if not match:
        raise DecodeError("no JSON object in decoded payload")
    candidate = match[0]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        if candidate.startswith("{"):
            retry = re.findall(r'\{"[\s\S]*', candidate[1:])
            if retry:
                return json.loads(retry[0])
        raise


def decode(data, jv: str = "") -> dict:
    """data 为响应 JSON 中的 data 字段（字符串）。"""
    if isinstance(data, dict):
        jv = data.get("jv", jv)
        data = data["data"]
    try:
        return _extract_json(base64.b64decode(data.encode("utf-8")).decode("utf-8"))
    except Exception:
        cleaned = _deobfuscate(data, jv)
        try:
            return _extract_json(base64.b64decode(cleaned.encode("utf-8")).decode("utf-8", errors="ignore"))
        except UnknownJv:
            raise
        except Exception as exc:
            raise DecodeError(f"jv decode failed (jv={jv}): {exc}") from exc
