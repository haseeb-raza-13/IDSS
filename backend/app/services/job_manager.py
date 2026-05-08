import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import redis

from app.config import settings

_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _key(job_id: str) -> str:
    return f"job:{job_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    """
    Redis-backed job state machine.

    Jobs have these fields stored as a Redis hash:
      job_id, type, status, steps (JSON), run_id, result (JSON), error,
      job_dir, created_at, updated_at
    """

    @staticmethod
    def create(job_type: str, job_dir: Path, job_id: Optional[str] = None) -> str:
        job_id = job_id or str(uuid.uuid4())
        now = _now()
        r = _get_redis()
        r.hset(
            _key(job_id),
            mapping={
                "job_id": job_id,
                "type": job_type,
                "status": "pending",
                "steps": json.dumps([]),
                "run_id": "",
                "result": "",
                "error": "",
                "job_dir": str(job_dir),
                "created_at": now,
                "updated_at": now,
            },
        )
        r.expire(_key(job_id), settings.job_max_age_hours * 3600)
        return job_id

    @staticmethod
    def get(job_id: str) -> Optional[dict[str, Any]]:
        r = _get_redis()
        raw = r.hgetall(_key(job_id))
        if not raw:
            return None
        raw["steps"] = json.loads(raw.get("steps", "[]"))
        raw["result"] = json.loads(raw["result"]) if raw.get("result") else None
        raw["error"] = raw.get("error") or None
        raw["run_id"] = raw.get("run_id") or None
        return raw

    @staticmethod
    def set_status(job_id: str, status: str, error: Optional[str] = None) -> None:
        r = _get_redis()
        updates: dict[str, str] = {"status": status, "updated_at": _now()}
        if error is not None:
            updates["error"] = error
        r.hset(_key(job_id), mapping=updates)

    @staticmethod
    def set_step(job_id: str, step_name: str, step_status: str, error: Optional[str] = None) -> None:
        r = _get_redis()
        raw_steps = r.hget(_key(job_id), "steps") or "[]"
        steps: list[dict] = json.loads(raw_steps)
        now = _now()

        existing = next((s for s in steps if s["name"] == step_name), None)
        if existing is None:
            step: dict[str, Any] = {
                "name": step_name,
                "status": step_status,
                "started_at": now if step_status == "running" else None,
                "finished_at": now if step_status in ("done", "failed") else None,
                "error": error,
            }
            steps.append(step)
        else:
            existing["status"] = step_status
            if step_status == "running" and not existing.get("started_at"):
                existing["started_at"] = now
            if step_status in ("done", "failed"):
                existing["finished_at"] = now
            if error is not None:
                existing["error"] = error

        r.hset(_key(job_id), mapping={"steps": json.dumps(steps), "updated_at": now})

    @staticmethod
    def set_run_id(job_id: str, run_id: str) -> None:
        _get_redis().hset(_key(job_id), mapping={"run_id": run_id, "updated_at": _now()})

    @staticmethod
    def set_result(job_id: str, result: dict[str, Any]) -> None:
        _get_redis().hset(
            _key(job_id),
            mapping={"result": json.dumps(result), "updated_at": _now()},
        )

    @staticmethod
    def cancel(job_id: str) -> bool:
        r = _get_redis()
        raw = r.hgetall(_key(job_id))
        if not raw:
            return False
        if raw.get("status") in ("done", "failed"):
            return False
        r.hset(_key(job_id), mapping={"status": "failed", "error": "Cancelled by user", "updated_at": _now()})
        return True

    @staticmethod
    def job_dir(job_id: str) -> Optional[Path]:
        r = _get_redis()
        val = r.hget(_key(job_id), "job_dir")
        return Path(val) if val else None
