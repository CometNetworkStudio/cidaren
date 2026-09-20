"""OmniTask Python 脚本运行时：stdio NDJSON 协议。

作者只需提供生成器 run(action, params, credentials)；本模块负责
读写 stdio、把进度事件按协议输出。详见 docs/script-protocol.md。
"""

import json
import sys


def serve(run_func) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except Exception:
            _emit({"type": "event", "event": "failed", "message": "invalid request json"})
            return
        if request.get("type") != "execute":
            continue
        task_id = request.get("task_id", "")
        try:
            for event in run_func(
                request.get("action", ""),
                request.get("params") or {},
                request.get("credentials") or {},
            ):
                _emit(
                    {
                        "type": "event",
                        "task_id": task_id,
                        "event": "progress",
                        "percent": int(event.get("percent", 0)),
                        "message": str(event.get("message", "")),
                        "result": event.get("result") or {},
                    }
                )
            _emit({"type": "event", "task_id": task_id, "event": "succeeded", "percent": 100, "message": "done", "result": {}})
        except Exception as exc:  # noqa: BLE001
            _emit(
                {
                    "type": "event",
                    "task_id": task_id,
                    "event": "failed",
                    "percent": 0,
                    "message": f"{type(exc).__name__}: {exc}",
                    "result": {},
                }
            )
        return


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()
