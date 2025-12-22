import json
from typing import Any, Dict, Optional

import redis
from app.core.config import settings

_r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def channel_for(job_id: str) -> str:
    return f"job:{job_id}:events"


def publish(job_id: str, payload: Dict[str, Any]) -> None:
    _r.publish(channel_for(job_id), json.dumps(payload))


def safe_publish(job_id: Optional[str], payload: Dict[str, Any]) -> None:
    if not job_id:
        return
    try:
        publish(job_id, payload)
    except Exception:
        pass
