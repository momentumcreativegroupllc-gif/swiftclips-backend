import json
import time
from typing import Generator, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from redis import Redis
from rq.job import Job

from app.core.config import settings
from app.repos.jobs_repo import list_jobs as db_list_jobs, DEMO_USER_ID
from app.repos.credits_repo import get_credits  # ✅ Day 13: credits endpoint

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/me")
def me():
    credits = get_credits(DEMO_USER_ID)
    return {"user_id": DEMO_USER_ID, "credits": credits}


@router.get("")
def list_jobs():
    return {"jobs": db_list_jobs(DEMO_USER_ID, limit=20)}


def _redis_conn_rq() -> Redis:
    # IMPORTANT: RQ needs raw bytes for some fields; do NOT decode responses here.
    return Redis.from_url(settings.REDIS_URL)


def _redis_conn_pubsub() -> Redis:
    # Pub/Sub messages are JSON strings; decoding is helpful here.
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _fetch_job(job_id: str) -> Job:
    try:
        return Job.fetch(job_id, connection=_redis_conn_rq())
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _safe_json_loads(s: str) -> Optional[dict]:
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _find_db_job(job_id: str) -> Optional[dict]:
    """
    Find the DB job row (Supabase public.jobs) that matches this RQ job_id.
    In our schema, DB column is jobs.job_id (text) which matches RQ job.id.
    """
    try:
        rows = db_list_jobs(DEMO_USER_ID, limit=200)
        return next((r for r in rows if r.get("job_id") == job_id), None)
    except Exception:
        return None


@router.get("/{job_id}")
def get_job_status(job_id: str):
    """
    ✅ IMPORTANT:
    - DB (Supabase) is the source of truth for status/stage/clip_url/error
    - RQ is best-effort for live meta + result (but can be "started" while DB is already "finished")
    """
    job = _fetch_job(job_id)
    db_row = _find_db_job(job_id) or {}

    db_status = db_row.get("status")
    db_stage = db_row.get("stage")
    db_clip_url = db_row.get("clip_url")
    db_error = db_row.get("error")

    # Prefer DB; fallback to RQ/meta if DB missing
    status = db_status or job.meta.get("status") or job.get_status()
    stage = db_stage or job.meta.get("stage")

    return {
        "job_id": job.id,
        "status": status,
        "stage": stage,
        "clip_url": db_clip_url,
        "meta": job.meta,
        "result": job.result if job.is_finished else None,
        "error": db_error or (str(job.exc_info) if job.is_failed else None),
    }


@router.get("/{job_id}/events")
def stream_job_events(job_id: str):
    # Ensure job exists before we open the stream
    job = _fetch_job(job_id)

    r = _redis_conn_pubsub()
    channel = f"job:{job_id}:events"
    pubsub = r.pubsub()
    pubsub.subscribe(channel)

    def gen() -> Generator[str, None, None]:
        last_ping = 0.0
        try:
            # Initial snapshot (helps refresh UX)
            # Prefer job.meta status if worker set it; fallback to RQ status
            initial_payload = {
                "job_id": job_id,
                "status": job.meta.get("status") or job.get_status(),
                "stage": job.meta.get("stage"),
                "meta": job.meta,
            }
            yield _sse("message", initial_payload)

            while True:
                msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

                if msg and msg.get("data"):
                    raw = msg["data"]  # JSON string from worker publish
                    payload = _safe_json_loads(raw)

                    if payload is None:
                        yield _sse("message", {"job_id": job_id, "raw": str(raw)})
                    else:
                        payload.setdefault("job_id", job_id)
                        yield _sse("message", payload)

                        # Worker publishes terminal statuses as strings
                        if payload.get("status") in ("finished", "failed"):
                            break

                now = time.time()
                if now - last_ping > 10:
                    last_ping = now
                    yield _sse("ping", {})

                time.sleep(0.1)

        except GeneratorExit:
            pass
        finally:
            try:
                pubsub.unsubscribe(channel)
                pubsub.close()
            except Exception:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream")
