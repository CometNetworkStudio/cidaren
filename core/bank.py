"""题库抽象。P1 用本地 SQLite 适配器；P3 起改用后端 gRPC QuestionBank 客户端。

question 字典字段（与 proto Question 对齐）：
    platform, question_key, stem, options(JSON 字符串), answer(JSON 字符串),
    source(bank|api|llm), confidence(float)
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path

import grpc

_SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    platform     TEXT NOT NULL,
    question_key TEXT NOT NULL,
    stem         TEXT NOT NULL DEFAULT '',
    options      TEXT NOT NULL DEFAULT '[]',
    answer       TEXT NOT NULL DEFAULT '{}',
    source       TEXT NOT NULL DEFAULT 'bank',
    confidence   REAL NOT NULL DEFAULT 0,
    hit_count    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (platform, question_key)
)
"""


class QuestionBank(ABC):
    @abstractmethod
    def lookup(self, platform: str, question_key: str) -> dict | None: ...

    @abstractmethod
    def save(self, question: dict, overwrite: bool = False) -> bool: ...


class LocalBank(QuestionBank):
    """P1 本地开发适配器，仅供 Agent 独立验证；不属于生产数据路径。"""

    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def lookup(self, platform: str, question_key: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM questions WHERE platform=? AND question_key=?",
                (platform, question_key),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE questions SET hit_count=hit_count+1 WHERE platform=? AND question_key=?",
                (platform, question_key),
            )
            self._conn.commit()
        return {
            "platform": row["platform"],
            "question_key": row["question_key"],
            "stem": row["stem"],
            "options": row["options"],
            "answer": row["answer"],
            "source": row["source"],
            "confidence": row["confidence"],
            "hit_count": row["hit_count"] + 1,
        }

    def save(self, question: dict, overwrite: bool = False) -> bool:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        values = {
            "platform": question["platform"],
            "question_key": question["question_key"],
            "stem": question.get("stem", ""),
            "options": _as_text(question.get("options", "[]")),
            "answer": _as_text(question.get("answer", "{}")),
            "source": question.get("source", "bank"),
            "confidence": float(question.get("confidence", 0.0)),
        }
        with self._lock:
            if overwrite:
                self._conn.execute(
                    """INSERT INTO questions
                       (platform,question_key,stem,options,answer,source,confidence,hit_count,created_at,updated_at)
                       VALUES (:platform,:question_key,:stem,:options,:answer,:source,:confidence,0,:now,:now)
                       ON CONFLICT(platform,question_key) DO UPDATE SET
                         stem=excluded.stem, options=excluded.options, answer=excluded.answer,
                         source=excluded.source, confidence=excluded.confidence, updated_at=excluded.updated_at""",
                    {**values, "now": now},
                )
            else:
                cur = self._conn.execute(
                    """INSERT OR IGNORE INTO questions
                       (platform,question_key,stem,options,answer,source,confidence,hit_count,created_at,updated_at)
                       VALUES (:platform,:question_key,:stem,:options,:answer,:source,:confidence,0,:now,:now)""",
                    {**values, "now": now},
                )
                if cur.rowcount == 0:
                    self._conn.commit()
                    return False
            self._conn.commit()
        return True

    def close(self) -> None:
        self._conn.close()


def _as_text(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class GrpcBank(QuestionBank):
    """经后端 gRPC QuestionBank 读写（生产路径，Agent 不直连数据库）。"""

    def __init__(self, addr: str, stub=None, pb2=None, timeout: float = 10.0) -> None:
        self.addr = addr
        self.timeout = timeout
        self._stub = stub
        self._pb2 = pb2
        self._channel = None

    def _ensure(self) -> None:
        if self._stub is not None:
            return
        import sys

        gen = Path(__file__).resolve().parents[1] / "gen"
        if str(gen) not in sys.path:
            sys.path.insert(0, str(gen))
        from agent.v1 import agent_pb2, agent_pb2_grpc

        self._pb2 = agent_pb2
        self._channel = grpc.insecure_channel(self.addr)
        self._stub = agent_pb2_grpc.QuestionBankStub(self._channel)

    def lookup(self, platform: str, question_key: str) -> dict | None:
        self._ensure()
        resp = self._stub.Lookup(
            self._pb2.LookupRequest(platform=platform, question_key=question_key),
            timeout=self.timeout,
        )
        if not resp.found:
            return None
        q = resp.question
        return {
            "platform": q.platform,
            "question_key": q.question_key,
            "stem": q.stem,
            "options": q.options,
            "answer": q.answer,
            "source": q.source,
            "confidence": q.confidence,
            "hit_count": q.hit_count,
        }

    def save(self, question: dict, overwrite: bool = False) -> bool:
        self._ensure()
        message = self._pb2.Question(
            platform=question["platform"],
            question_key=question["question_key"],
            stem=question.get("stem", ""),
            options=_as_text(question.get("options", "[]")),
            answer=_as_text(question.get("answer", "{}")),
            source=question.get("source", "bank"),
            confidence=float(question.get("confidence", 0.0)),
        )
        resp = self._stub.Save(
            self._pb2.SaveRequest(question=message, overwrite=overwrite),
            timeout=self.timeout,
        )
        return bool(resp.saved)

    def close(self) -> None:
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None
