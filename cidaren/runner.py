"""词达人 runner：题库 → LLM → 跳过；支持班级学习/测试任务。

真实流程（已联调验证）：
    ClassTask/PageTask 取任务 → 按 task_name 匹配 StudyTask/List 单元 →
    StudyTask/Info 取词表 → (task_type=1) SubmitChoseWord →
    ClassTask/StartAnswer → 逐题 VerifyAnswer/SubmitAnswerAndSave，mode 0 为阅读卡直接跳过。
"""

from __future__ import annotations

import random
import time

from core.bank import GrpcBank, LocalBank
from core.config import Config
from core.events import event
from core.llm import LLMClient
from core.params import resolve
from core.ratelimit import RateLimiter

from . import answer as answer_mod
from .client import CidarenClient, CidarenError, SecurityVerifyError

MAX_QUESTIONS = 1000
MAX_PAGES = 20
TASK_KIND = "ClassTask"
TASK_TYPE_INT = 2  # 班级任务协议固定为 2（无论 record.task_type 是 1 还是 2）

_CONFIG = Config.from_env()


def _bank():
    if _CONFIG.bank_mode == "grpc":
        return GrpcBank(_CONFIG.bank_addr)
    return LocalBank(_CONFIG.bank_local_path)


def _all_class_tasks(client: CidarenClient) -> list:
    tasks, page = [], 1
    while page <= MAX_PAGES:
        data = client.list_class_tasks(page)
        records = (data or {}).get("records") or []
        tasks.extend(records)
        total = (data or {}).get("total") or 0
        if not records or len(tasks) >= total:
            break
        page += 1
    return tasks


def _select_tasks(tasks: list, params: dict) -> list:
    want_type = params.get("task_type")
    want_name = params.get("task_name")
    progress_lt = int(params.get("progress_lt", 100))
    picked = []
    for task in tasks:
        if task.get("over_status") == 3:
            continue
        if want_type not in (None, "") and int(task.get("task_type", 0)) != int(want_type):
            continue
        if want_name and want_name not in str(task.get("task_name", "")):
            continue
        if int(task.get("progress") or 0) >= progress_lt:
            continue
        picked.append(task)
    limit = params.get("limit")
    return picked[: int(limit)] if limit else picked


def _prepare_words(client: CidarenClient, task: dict) -> None:
    """按 task_name 匹配单元；task_type=1 需先 SubmitChoseWord（已开启则忽略错误）。"""
    course_id = task["course_id"]
    units = client.list_study_tasks(course_id).get("task_list") or []
    unit = next((u for u in units if u.get("task_name") == task.get("task_name")), None)
    if unit is None:
        return
    info = client.study_task_info(unit["task_id"], course_id, list_id=unit["list_id"])
    words = [w["word"] for w in info.get("word_list") or [] if isinstance(w, dict) and w.get("word")]
    if not words or int(task.get("task_type") or 0) != 1:
        return
    try:
        client.submit_chose_word(TASK_KIND, task["task_id"], {f"{course_id}:{unit['list_id']}": words})
    except CidarenError:
        pass  # 任务已开启，继续答题即可


def _run_task(client: CidarenClient, task: dict, llm, bank, params: dict):
    name = task.get("task_name")
    # 思考延迟：答完一题后停一会，模拟人类（参考默认 2s）。
    think_min = float(params.get("think_min", 2))
    think_max = float(params.get("think_max", max(think_min, 2)))
    # 服务端 time_spent：本题“用时”，单位 500=1 秒（参考默认 5~15s）。
    spend_min = int(params.get("spend_min", 5))
    spend_max = int(params.get("spend_max", 15))
    _prepare_words(client, task)

    started = client.start_answer(task["task_id"], TASK_KIND, TASK_TYPE_INT, release_id=task.get("release_id"))
    if started.get("done"):
        yield event(100, f"{name}: 任务已完成({started.get('msg')})")
        return
    exam = started["exam"]
    total = exam.get("topic_total") or MAX_QUESTIONS
    max_steps = int(params.get("max_steps", MAX_QUESTIONS))
    for _ in range(max_steps):
        mode = exam.get("topic_mode")
        if mode == 0:  # 阅读卡：直接跳读
            step = client.next_question(TASK_KIND, exam["topic_code"], spend_min, spend_max)
            time.sleep(random.uniform(1, 3))
        else:
            submission = None
            if mode not in answer_mod.UNSUPPORTED_MODES:
                record = bank.lookup("cidaren", answer_mod.question_key(exam))
                if record:
                    submission = answer_mod.resolve_from_record(exam, record["answer"])
                if submission is None and llm.config.enabled:
                    try:
                        submission = answer_mod.llm_answer(exam, llm)
                    except Exception:
                        submission = None
            if submission is None:
                step = client.skip_answer(TASK_KIND, exam["topic_code"])
            else:
                result = client.verify_answer(TASK_KIND, exam["topic_code"], submission)
                bank.save(answer_mod.derive_record(exam, result), overwrite=True)
                step = client.next_question(TASK_KIND, result["topic_code"], spend_min, spend_max)
            time.sleep(random.uniform(think_min, think_max))

        done = exam.get("topic_done_num") or 0
        yield event(int(done / total * 100), f"{name}: {done}/{total}")
        if step.get("done"):
            yield event(100, f"{name}: 完成({step.get('msg')})")
            return
        exam = step["exam"]
    yield event(100, f"{name}: 达到单任务题量上限，提前结束")


def run(action: str, params: dict, credentials: dict):
    token = credentials.get("token") or params.get("token")
    if not token:
        raise CidarenError("词达人需要 token 凭据")
    resolved = resolve("cidaren", params, _CONFIG)
    limiter = RateLimiter(
        resolved["platform_concurrency"],
        resolved["request_min_interval"],
        resolved["request_max_interval"],
    )
    client = CidarenClient(token, _CONFIG, limiter)
    llm = LLMClient(_CONFIG.llm)
    bank = _bank()
    try:
        user = client.token_check()
        nick = (user.get("user_info") or {}).get("nick_name", "")
        yield event(1, f"token 校验通过 user={nick}".strip())
        tasks = _select_tasks(_all_class_tasks(client), resolved)
        if not tasks:
            yield event(100, "没有可执行任务")
            return
        yield event(2, f"待执行任务 {len(tasks)} 个")
        for task in tasks:
            for evt in _run_task(client, task, llm, bank, resolved):
                yield evt
        yield event(100, "全部任务结束")
    except SecurityVerifyError as exc:
        raise CidarenError(str(exc)) from exc
    finally:
        bank.close()
