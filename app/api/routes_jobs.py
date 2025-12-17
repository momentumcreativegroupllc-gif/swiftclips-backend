import json
import time
from typing import Generator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from redis import Redis
from rq.job import Job

from app.core.config import settings
from app.repos.jobs_repo import list_jobs as db_list_jobs, DEMO_USER_ID


router = APIRouter(prefix="/jobs", tags=["jobs"])
@router.get("")
def list_jobs():
    return {"jobs": db_list_jobs(DEMO_USER_ID, limit=20)}

def _redis_conn() -> Redis:
    return Redis.from_url(settings.REDIS_URL)

def _fetch_job(job_id: str) -> Job:
    try:
        return Job.fetch(job_id, connection=_redis_conn())
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

@router.get("/{job_id}")
def get_job_status(job_id: str):
    job = _fetch_job(job_id)
    return {
        "job_id": job.id,
        "status": job.get_status(),
        "stage": job.meta.get("stage"),
        "meta": job.meta,
        "result": job.result if job.is_finished else None,
        "error": str(job.exc_info) if job.is_failed else None,
    }

@router.get("/{job_id}/events")
def stream_job_events(job_id: str):
    _fetch_job(job_id)  # ensure exists

    def gen() -> Generator[str, None, None]:
        last_status = None
        last_stage = None

        while True:
            job = _fetch_job(job_id)
            status = job.get_status()
            stage = job.meta.get("stage")

            if status != last_status:
                yield _sse("status", {"job_id": job_id, "status": status})
                last_status = status

            if stage != last_stage and stage is not None:
                payload = {"job_id": job_id, "stage": stage}
                # include useful fields when present
                for k in ("video_id", "scene_time", "clip_url"):
                    if k in job.meta:
                        payload[k] = job.meta[k]
                yield _sse("stage", payload)
                last_stage = stage

            if job.is_finished:
                yield _sse("done", {"job_id": job_id, "result": job.result})
                break

            if job.is_failed:
                yield _sse("error", {"job_id": job_id, "error": str(job.exc_info)})
                break

            time.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")
