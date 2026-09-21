import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from omnitask_sdk import listing
from omnitask_sdk.config import Config
from omnitask_sdk.ratelimit import RateLimiter
from omnitask_sdk.runtime import serve

from cidaren.runner import run

_CONFIG = Config.from_env()


def _client(credentials):
    from cidaren.client import CidarenClient

    token = credentials.get("token") or ""
    if not token:
        raise RuntimeError("缺少 token 凭据")
    limiter = RateLimiter(
        _CONFIG.platform_concurrency,
        _CONFIG.request_min_interval,
        _CONFIG.request_max_interval,
    )
    return CidarenClient(token, _CONFIG, limiter)


@listing()
def tasks(ctx):
    """发现：列出该账号的班级任务（供 OmniTask 选择）。"""
    client = _client(ctx.credentials)
    page = client.list_class_tasks(1)
    records = (page or {}).get("records") or []
    return [
        {
            "key": str(r.get("task_id")),
            "fields": {
                "task_name": str(r.get("task_name") or ""),
                "course_id": str(r.get("course_id") or ""),
                "task_type": str(r.get("task_type") or ""),
                "progress": str(r.get("progress") or ""),
                "release_id": str(r.get("release_id") or ""),
            },
        }
        for r in records
    ]


def main():
    if sys.stdin.isatty() or "--cli" in sys.argv:
        from cli import main as cli_main

        return cli_main()
    serve(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
