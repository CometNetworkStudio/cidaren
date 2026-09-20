"""Runner 进度事件约定（与 proto ExecuteEvent 对应）。"""

from __future__ import annotations


def clamp_percent(value: int) -> int:
    return max(0, min(100, int(value)))


def event(percent: int, message: str, result: dict | None = None) -> dict:
    """构造一个进度事件；runner.run 逐条 yield 该结构。"""
    return {"percent": clamp_percent(percent), "message": str(message), "result": result or {}}
