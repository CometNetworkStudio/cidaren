"""答题策略：题库 → LLM → 跳过。

修正认知（见 reference-analysis）：`options[].answer_tag` 是每个选项的**提交码**，
不是“正确项”标记，故不能作为提示。正确性只有 `VerifyAnswer.answer_corrects` 权威。
"""

from __future__ import annotations

import hashlib
import json

OPTION_MODES = {11, 13, 15, 16, 17, 18, 21, 22, 41, 42, 43, 44}
TEXT_MODES = {32, 51, 52, 53, 54, 73}
UNSUPPORTED_MODES = {31}


def question_key(exam: dict) -> str:
    mode = exam.get("topic_mode")
    stem = exam.get("stem") or {}
    content = stem.get("content", "") if isinstance(stem, dict) else ""
    remark = stem.get("remark", "") if isinstance(stem, dict) else ""
    raw = f"{mode}|{content}|{remark}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _option_contents(exam: dict) -> list:
    return [
        opt.get("content")
        for opt in (exam.get("options") or [])
        if isinstance(opt, dict)
    ]


def _option_tag(option: dict, index: int):
    tag = option.get("answer_tag")
    return index if tag is None else tag


def derive_record(exam: dict, result: dict) -> dict:
    """把 VerifyAnswer 的权威结果整理为入库记录（answer 为 JSON 字符串）。"""
    mode = exam.get("topic_mode")
    corrects = result.get("answer_corrects")
    payload = {
        "mode": mode,
        "corrects": corrects,
        "options": _option_contents(exam),
    }
    return {
        "platform": "cidaren",
        "question_key": question_key(exam),
        "stem": json.dumps(exam.get("stem") or {}, ensure_ascii=False),
        "options": json.dumps(exam.get("options") or [], ensure_ascii=False),
        "answer": json.dumps(payload, ensure_ascii=False),
        "source": "api",
        "confidence": 1.0,
    }


def resolve_from_record(exam: dict, record_answer: str):
    """用题库记录在当前题面上还原出可直接提交的 answer。失败返回 None。"""
    try:
        payload = json.loads(record_answer)
    except (TypeError, json.JSONDecodeError):
        return None
    mode = payload.get("mode")
    corrects = payload.get("corrects")
    options = exam.get("options") or []

    if mode in OPTION_MODES:
        stored = payload.get("options") or []
        if isinstance(corrects, int):
            corrects = [corrects]
        if not isinstance(corrects, list):
            return corrects
        wanted = [stored[i] for i in corrects if isinstance(i, int) and 0 <= i < len(stored)]
        tags = []
        for content in wanted:
            for index, opt in enumerate(options):
                if isinstance(opt, dict) and opt.get("content") == content:
                    tags.append(_option_tag(opt, index))
                    break
        if not tags:
            return None
        return tags[0] if len(tags) == 1 else tags

    if mode == 73:
        if isinstance(corrects, list):
            return json.dumps(corrects, ensure_ascii=False)
        return corrects
    if mode == 32:
        if isinstance(corrects, list):
            return ",".join(str(x) for x in corrects)
        return corrects
    return corrects


def llm_answer(exam: dict, llm) -> object:
    mode = exam.get("topic_mode")
    stem = exam.get("stem") or {}
    content = stem.get("content", "") if isinstance(stem, dict) else ""
    remark = stem.get("remark", "") if isinstance(stem, dict) else ""
    options = exam.get("options") or []
    option_lines = []
    for index, opt in enumerate(options):
        if isinstance(opt, dict):
            option_lines.append(f"{index}: {opt.get('content')}")
    option_text = "\n".join(option_lines)
    prompt = (
        f"题型编号：{mode}\n题干：{content}\n中文提示：{remark}\n"
        f"选项（若为空则此题需要文本作答）：\n{option_text}\n\n"
        "请只输出 JSON：选择题输出 {\"index\": 正确选项编号}；"
        "填空/拼写输出 {\"text\": \"答案\"}；mode 73 输出 {\"words\": [\"词1\",\"词2\"]}。"
    )
    import re

    raw = llm.complete(prompt, system="你是英语题目作答器，只输出要求的 JSON。")
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError(f"LLM 未返回 JSON: {raw[:120]}")
    data = json.loads(match.group(0))
    if "index" in data:
        index = int(data["index"])
        if not (0 <= index < len(options)):
            raise ValueError("LLM 选项越界")
        return _option_tag(options[index], index)
    if "words" in data:
        return json.dumps(data["words"], ensure_ascii=False)
    if "text" in data:
        return data["text"]
    raise ValueError("LLM 返回缺少答案字段")
