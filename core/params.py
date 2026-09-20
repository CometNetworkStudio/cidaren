"""任务参数默认值与合并规则。

约定：
- 用户通过任务 params 自定义；程序用本文件默认值兜底。
- `.env` 只提供基础设施级兜底（并发/节流），可被任务 params 覆盖。
- 后端 M2 会把用户 params 存进 `Task.Params`，经 gRPC 原样下发。
"""

from __future__ import annotations

COMMON_DEFAULTS = {
    "platform_concurrency": 2,
    "request_min_interval": 0.8,
    "request_max_interval": 2.5,
}

DEFAULTS = {
    "cidaren": {
        "think_min": 2.0,  # 答完一题后的思考停顿（秒）
        "think_max": 4.0,
        "spend_min": 5,  # 服务端 time_spent，单位 500=1s
        "spend_max": 15,
        "task_type": 1,  # 1 班级学习 / 2 班级测试
        "progress_lt": 100,  # 只处理进度低于该值的任务
        "limit": 0,  # 0 = 不限制任务数
        "max_steps": 1000,  # 单任务最多推进题数
    },
    "welearn": {
        "duration": 60,  # 挂时长秒数
        "accuracy": 100,  # 提交进度正确率
        "include_completed": False,
        "limit": 0,  # 0 = 不限制 SCO 数
    },
}

_INT_KEYS = {"spend_min", "spend_max", "task_type", "progress_lt", "limit", "max_steps", "duration"}
_FLOAT_KEYS = {"think_min", "think_max", "platform_concurrency", "request_min_interval", "request_max_interval"}
_BOOL_KEYS = {"include_completed"}


def _coerce(key: str, value):
    if isinstance(value, str):
        value = value.strip()
    if key in _INT_KEYS:
        return int(value)
    if key in _FLOAT_KEYS:
        return float(value)
    if key in _BOOL_KEYS:
        return str(value).lower() in ("1", "true", "yes", "on")
    return value


def resolve(platform: str, params: dict | None, config=None) -> dict:
    """默认值 < 基础设施(env) < 用户 params。"""
    resolved = dict(COMMON_DEFAULTS)
    resolved.update(DEFAULTS.get(platform, {}))
    if config is not None:
        resolved.update(
            {
                "platform_concurrency": config.platform_concurrency,
                "request_min_interval": config.request_min_interval,
                "request_max_interval": config.request_max_interval,
            }
        )
    for key, value in (params or {}).items():
        if key in resolved:
            resolved[key] = _coerce(key, value)
        else:
            resolved[key] = value  # 透传未知参数（如 task_name）
    return resolved
