"""词达人 HTTP 客户端（净室重写，仅实现协议行为）。

凭据只有 Token；base_url / 请求头 / 端点与签名规则见 `docs/reference-analysis.md`。
"""

from __future__ import annotations

import json
import random
import time

import requests

from omnitask_sdk import http
from . import jv as jvmod
from .sign import build_sign, md5_hex

BASE_URL = "https://app.vocabgo.com/student/api/Student/"
UA = (
    "Mozilla/5.0 (Linux; Android 8.1.2; LIO-AN00 Build/LIO-AN00; wv) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.131 Safari/537.36 MMWEBID/4462 "
    "MicroMessenger/8.0.20.2100(0x28001438) Process/toolsmp WeChat/arm64 Weixin Android Tablet "
    "NetType/WIFI Language/zh_CN ABI/arm64"
)
AUTH_READ = "cfcd208495d565ef66e7dff9f98764da"
AUTH_SUBMIT = "c4ca4238a0b923820dcc509a6f75849b"

VERSION_261 = "2.6.1.231204"
VERSION_262 = "2.6.2.24031302"
VERSION_SUBMIT = "2.6.1.231204"

KNOWN_CODES_COMPLETE = {20001, 20004}


class SecurityVerifyError(RuntimeError):
    """11003：需人工在 App/微信完成安全验证，重试无意义。"""


class CidarenError(RuntimeError):
    pass


def _base_headers(token: str, auth: str, submit: bool = False) -> dict:
    headers = {
        "Host": "app.vocabgo.com",
        "Accept": "application/json, text/plain, */*",
        "Abc": md5_hex(UA),
        "Authorization-V": auth,
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": UA,
        "Accept-Language": "*",
        "Referer": "https://app.vocabgo.com/student/",
        "Accept-Encoding": "gzip, deflate, br",
        "Usertoken": token,
    }
    if submit:
        headers.update({"Origin": "https://app.vocabgo.com", "Content-Type": "application/json"})
    return headers


def _timestamp() -> int:
    return int(time.time() * 1000)


class CidarenClient:
    def __init__(self, token: str, config, limiter=None) -> None:
        self.token = token
        self.config = config
        self.limiter = limiter
        if not token:
            raise CidarenError("missing token")
        self._read = http.new_session(
            _base_headers(token, AUTH_READ),
            retries=config.http_retries,
            proxy=config.http_proxy,
            timeout=config.http_timeout,
        )
        self._submit = http.new_session(
            _base_headers(token, AUTH_SUBMIT, submit=True),
            retries=config.http_retries,
            proxy=config.http_proxy,
            timeout=config.http_timeout,
        )

    def _guard(self):
        if self.limiter is None:
            return _null_ctx()
        return self.limiter.account_slot("cidaren", self.token[-8:])

    def _send(self, method: str, path: str, *, params=None, body=None, submit=False):
        session = self._submit if submit else self._read
        url = BASE_URL + path
        for _ in range(5):
            with self._guard():
                if method == "GET":
                    resp = http.request(session, "GET", url, params=params)
                else:
                    resp = http.request(session, "POST", url, data=json.dumps(body))
            payload = resp.json()
            if jvmod.is_known_jv(payload.get("jv", "")):
                return payload
            time.sleep(random.uniform(2, 3))
        raise jvmod.DecodeError("jv 连续 5 次不在已知集合")

    def _check(self, payload: dict) -> dict:
        code = payload.get("code")
        if code == 11003:
            raise SecurityVerifyError("服务端需安全验证，请在 App/微信完成验证后重试")
        if code == 1:
            return payload
        if code in KNOWN_CODES_COMPLETE and payload.get("data"):
            return payload
        raise CidarenError(f"接口错误 code={code} msg={payload.get('msg')}")

    def _data(self, payload: dict):
        """列表类接口 data 为明文；答题类接口 data 为 jv/base64 字符串。"""
        self._check(payload)
        data = payload.get("data")
        if isinstance(data, str):
            return jvmod.decode(data, payload.get("jv", ""))
        return data

    # ---- 账户 ----
    def token_check(self) -> dict:
        payload = self._send("GET", "Main", params={"timestamp": _timestamp(), "version": VERSION_261, "app_type": 1})
        return self._check(payload).get("data", {})

    # ---- 任务列表 ----
    def list_study_tasks(self, course_id: str) -> list:
        payload = self._send(
            "GET",
            "StudyTask/List",
            params={"course_id": course_id, "timestamp": _timestamp(), "version": VERSION_261, "app_type": 1},
        )
        return self._data(payload)

    def list_class_tasks(self, page_count: int = 1) -> dict:
        params = {
            "page_count": page_count,
            "page_size": 10,
            "search_type": 0,
            "timestamp": _timestamp(),
            "version": VERSION_261,
        }
        body = {
            "search_type": "0",
            "page_count": params["page_count"],
            "page_size": 10,
            "timestamp": params["timestamp"],
            "version": VERSION_261,
            "sign": build_sign(params),
            "app_type": 1,
        }
        payload = self._send("POST", "ClassTask/PageTask", body=body, submit=True)
        return self._data(payload)

    def study_task_info(self, task_id, course_id, list_id=None, release_id=None) -> dict:
        params = {
            "task_id": task_id or -1,
            "course_id": course_id,
            "timestamp": _timestamp(),
            "version": "2.6.1.240305",
            "app_type": 1,
        }
        if release_id:
            params["release_id"] = release_id
        else:
            params["list_id"] = list_id
        return self._data(self._send("GET", "StudyTask/Info", params=params))

    # ---- 答题 ----
    def start_answer(self, task_id, task_type: str, task_type_int: int, course_id=None, release_id=None) -> dict:
        params = {
            "task_id": task_id or -1,
            "task_type": task_type_int,
            "opt_img_w": "684",
            "opt_font_size": "37",
            "opt_font_c": "%23000000",
            "it_img_w": "804",
            "it_font_size": "42",
            "timestamp": _timestamp(),
            "version": VERSION_SUBMIT,
            "app_type": "1",
        }
        if task_type_int == 2:
            params["release_id"] = release_id
        else:
            params["course_id"] = course_id
        payload = self._send("GET", f"{task_type}/StartAnswer", params=params)
        self._check(payload)
        if payload.get("msg") in ("任务已完成！", "需要选词！"):
            return {"done": True, "msg": payload.get("msg")}
        return {"done": False, "exam": jvmod.decode(payload["data"], payload.get("jv", ""))}

    def verify_answer(self, task_type: str, topic_code: str, answer) -> dict:
        params = {"answer": answer, "timestamp": _timestamp(), "topic_code": topic_code, "version": VERSION_SUBMIT}
        body = {**params, "sign": build_sign(params), "app_type": 1}
        payload = self._send("POST", f"{task_type}/VerifyAnswer", body=body, submit=True)
        return jvmod.decode(self._check(payload)["data"], payload.get("jv", ""))

    def next_question(self, task_type: str, topic_code: str, min_time: int, max_time: int) -> dict:
        params = {
            "it_font_size": 42,
            "it_img_w": 804,
            "opt_font_c": "#000000",
            "opt_font_size": 37,
            "opt_img_w": 684,
            "time_spent": random.randint(min_time * 500, max_time * 500),
            "timestamp": _timestamp(),
            "topic_code": topic_code,
            "version": VERSION_262,
        }
        body = {**params, "sign": build_sign(params)}
        payload = self._send("POST", f"{task_type}/SubmitAnswerAndSave", body=body, submit=True)
        self._check(payload)
        if payload.get("msg") in ("任务已完成！", "需要选词！"):
            return {"done": True, "msg": payload.get("msg")}
        return {"done": False, "exam": jvmod.decode(payload["data"], payload.get("jv", ""))}

    def skip_answer(self, task_type: str, topic_code: str, time_spent: int = 20000) -> dict:
        params = {
            "it_font_size": 42,
            "it_img_w": 804,
            "opt_font_c": "#000000",
            "opt_font_size": 37,
            "opt_img_w": 684,
            "time_spent": time_spent,
            "timestamp": _timestamp(),
            "topic_code": topic_code,
            "version": VERSION_262,
        }
        body = {**params, "sign": build_sign(params)}
        payload = self._send("POST", f"{task_type}/SkipAnswer", body=body, submit=True)
        self._check(payload)
        if payload.get("msg") in ("任务已完成！", "需要选词！"):
            return {"done": True, "msg": payload.get("msg")}
        return {"done": False, "exam": jvmod.decode(payload["data"], payload.get("jv", ""))}

    def submit_chose_word(self, task_type: str, task_id, word_map: dict) -> bool:
        timestamp = _timestamp()
        params = {
            "chose_err_item": 2,
            "task_id": task_id,
            "timestamp": timestamp,
            "version": VERSION_261,
            "word_map": json.dumps(word_map, separators=(",", ":")),
        }
        body = {
            "task_id": task_id,
            "word_map": word_map,
            "chose_err_item": 2,
            "timestamp": timestamp,
            "version": VERSION_261,
            "sign": build_sign(params),
            "app_type": 1,
        }
        payload = self._send("POST", f"{task_type}/SubmitChoseWord", body=body, submit=True)
        self._check(payload)
        return True

    def query_word(self, course_id: str, list_id: str, word: str) -> dict:
        params = {
            "course_id": course_id,
            "list_id": list_id,
            "word": word,
            "timestamp": _timestamp(),
            "version": VERSION_261,
            "app_type": 1,
        }
        return self._data(self._send("GET", "Course/StudyWordInfo", params=params))


class _null_ctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
