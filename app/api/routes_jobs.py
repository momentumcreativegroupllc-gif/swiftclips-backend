import json
import time
from typing import Generator, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from redis import Redis
from rq.job import Job

from app.core.config import settings
from app.deps.auth import get_current_user_id
from app.services.queue import queue  # retry enqueue

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Day 14 timeout protection (per job)
JOB_TIMEOUT_SECONDS = 10 * 60  # 10 minutes


def _redis_conn_rq() -> Redis:
    return Redis.from_url(settings.REDIS_URL)


def _redis_conn_pubsub() -> Redis:
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


def _db_get_job(job_id: str) -> Optional[dict]:
    from app.repos.jobs_repo import get_job as repo_get_job
    return repo_get_job(job_id)


def _db_list_jobs(user_id: str, limit: int = 20):
    from app.repos.jobs_repo import list_jobs as repo_list_jobs
    return repo_list_jobs(user_id, limit=limit)


def _db_get_credits(user_id: str) -> int:
    from app.repos.credits_repo import get_credits
    return get_credits(user_id)


def _pick_error(db_row: dict, rq_job: Job) -> Optional[str]:
    # DB is source of truth
    e = (db_row.get("error_reason") or db_row.get("error") or "").strip()
    if e:
        return e

    # fallback to RQ meta (NOT traceback)
    meta = rq_job.meta or {}
    e2 = (meta.get("error_reason") or meta.get("error") or "").strip()
    return e2 or None


@router.get("/me")
def me(user_id: str = Depends(get_current_user_id)):
    return {"user_id": user_id, "credits": _db_get_credits(user_id)}


@router.get("")
def list_jobs(user_id: str = Depends(get_current_user_id)):
    return {"jobs": _db_list_jobs(user_id, limit=20)}


@router.get("/{job_id}")
def get_job_status(job_id: str, user_id: str = Depends(get_current_user_id)):
    job = _fetch_job(job_id)
    db_row = _db_get_job(job_id) or {}

    # Ownership check (DB is source of truth)
    if not db_row or db_row.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Job not found")

    status = db_row.get("status") or job.meta.get("status") or job.get_status()
    stage = db_row.get("stage") or job.meta.get("stage")
    clip_url = db_row.get("clip_url")

    error_reason = _pick_error(db_row, job)

    return {
        "job_id": job.id,
        "status": status,
        "stage": stage,
        "clip_url": clip_url,
        "meta": job.meta,  # ok (no traceback)
        "result": job.result if job.is_finished else None,
        # IMPORTANT: do NOT return job.exc_info (traceback)
        "error": error_reason,
        "error_reason": error_reason,
    }


@router.get("/{job_id}/events")
def stream_job_events(job_id: str, user_id: str = Depends(get_current_user_id)):
    # Ensure job exists (RQ) + enforce ownership (DB)
    job = _fetch_job(job_id)
    db_row = _db_get_job(job_id) or {}

    if not db_row or db_row.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Job not found")

    r = _redis_conn_pubsub()
    channel = f"job:{job_id}:events"
    pubsub = r.pubsub()
    pubsub.subscribe(channel)

    def gen() -> Generator[str, None, None]:
        last_ping = 0.0
        try:
            # initial snapshot (clean)
            initial_error = _pick_error(db_row, job)

            initial_payload = {
                "job_id": job_id,
                "status": db_row.get("status") or job.meta.get("status") or job.get_status(),
                "stage": db_row.get("stage") or job.meta.get("stage"),
                "error_reason": initial_error,
            }
            yield _sse("message", initial_payload)

            while True:
                msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("data"):
                    raw = msg["data"]
                    payload = _safe_json_loads(raw) or {"raw": str(raw)}
                    payload.setdefault("job_id", job_id)

                    # ensure no traceback fields leak
                    payload.pop("exc_info", None)

                    yield _sse("message", payload)

                    if payload.get("status") in ("finished", "failed"):
                        break

                now = time.time()
                if now - last_ping > 10:
                    last_ping = now
                    yield _sse("ping", {})

                time.sleep(0.1)
        finally:
            try:
                pubsub.unsubscribe(channel)
                pubsub.close()
            except Exception:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/{job_id}/retry")
def retry_job(job_id: str, user_id: str = Depends(get_current_user_id)):
    from app.repos.jobs_repo import reset_job_for_retry

    db_row = _db_get_job(job_id)
    if not db_row or db_row.get("user_id") != user_id:
        # 404 to avoid leaking existence of other users' jobs
        raise HTTPException(status_code=404, detail="Job not found")

    source_url = db_row.get("source_video_url")
    if not source_url:
        raise HTTPException(status_code=400, detail="Job cannot be retried (missing source_video_url)")

    reset_job_for_retry(job_id)

    queue.enqueue(
        "app.workers.video_jobs.process_video_job",
        db_row.get("video_id") or job_id,
        source_url,
        job_id=job_id,
        job_timeout=JOB_TIMEOUT_SECONDS,
        result_ttl=60 * 60,
        failure_ttl=24 * 60 * 60,
    )

    return {"ok": True, "job_id": job_id}
