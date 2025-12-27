import os
import tempfile
import requests
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict

from rq import get_current_job
from rq.timeouts import JobTimeoutException

from app.services.progress_pubsub import safe_publish
from app.services.video_meta import get_duration_seconds
from app.services.scenes import detect_scene_timestamps
from app.services.clipper import cut_clip
from app.services.storage import upload_video_file
from app.repos.jobs_repo import update_job

from app.repos.credits_repo import decrement_credit_if_not_charged  # ✅ Day 13
from app.services.supabase_client import get_supabase  # ✅ Day 13

from app.core.job_constants import (
    STATUS_STARTED,
    STATUS_FINISHED,
    STATUS_FAILED,
    STAGE_DOWNLOADING,
    STAGE_ANALYZING,
    STAGE_CUTTING,
    STAGE_UPLOADING,
    STAGE_DONE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _publish(job_key: Optional[str], payload: Dict) -> None:
    """Safe wrapper so publish never breaks the worker."""
    try:
        safe_publish(job_key, payload)
    except Exception:
        pass


def _set_stage(stage: str, extra: Optional[Dict] = None) -> None:
    """
    Update RQ job meta + publish real-time progress event for SSE.
    Adds Day 14 heartbeat and default status rules.
    """
    job = get_current_job()
    if not job:
        return

    job.meta["stage"] = stage
    job.meta["last_heartbeat"] = _now()

    # Respect caller status if present, otherwise default to processing
    if extra and "status" in extra:
        job.meta["status"] = extra["status"]
    else:
        if job.meta.get("status") not in (STATUS_FINISHED, STATUS_FAILED):
            job.meta["status"] = "processing"

    if extra:
        job.meta.update(extra)

    job.save_meta()

    _publish(
        job.id,
        {
            "status": job.meta.get("status", "processing"),
            "stage": stage,
            **(extra or {}),
        },
    )


def download_file(url: str, dst_path: str) -> None:
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dst_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def _db_update(effective_job_id: Optional[str], fields: Dict) -> None:
    """Best-effort DB update that never kills the worker."""
    if not effective_job_id:
        return
    try:
        update_job(effective_job_id, fields)
    except Exception as e:
        print(f"[worker] DB update failed for job_id={effective_job_id}: {e}")


def process_video_job(video_id: str, storage_url: str, job_id: Optional[str] = None):
    """
    Day 14 goals:
    - No job stuck forever
    - Timeout protection + clear error reason in DB + RQ meta
    - Retry-ready (failed state is explicit)
    """
    job = get_current_job()

    # Determine the "public" job id string we use everywhere (DB jobs.job_id)
    effective_job_id = job_id or (job.id if job else None)

    # ✅ Day 13: fetch user_id ONCE (needed for credit charging)
    user_id = None
    if effective_job_id:
        try:
            sb = get_supabase()
            db_job = (
                sb.table("jobs")
                .select("user_id")
                .eq("job_id", effective_job_id)  # job_id (text), NOT id (uuid)
                .single()
                .execute()
            )
            user_id = db_job.data.get("user_id")
        except Exception as e:
            print(f"[worker] Failed to fetch user_id for job_id={effective_job_id}: {e}")

    # Mark started in meta + DB (Day 14 adds timestamps + heartbeat)
    if job:
        job.meta["status"] = STATUS_STARTED
        job.meta["stage"] = STAGE_DOWNLOADING
        job.meta["started_at"] = _now()
        job.meta["last_heartbeat"] = _now()
        job.meta.pop("error", None)
        job.meta.pop("error_reason", None)
        job.meta.pop("error_trace", None)
        job.save_meta()

        _publish(
            job.id,
            {
                "status": "processing",
                "stage": STAGE_DOWNLOADING,
                "video_id": video_id,
            },
        )

    _db_update(
        effective_job_id,
        {
            "status": "processing",
            "stage": STAGE_DOWNLOADING,
            "error": None,
            "error_reason": None,
            "started_at": _now(),
        },
    )

    try:
        _set_stage(STAGE_DOWNLOADING, {"video_id": video_id})
        print(f"[worker] started video_id={video_id} job_id={effective_job_id}")

        # ✅ Day 14 TEST: force failure INSIDE try so it gets written to DB/meta/SSE
        if os.getenv("SWIFTCLIPS_FAIL_TEST") == "1":
            raise RuntimeError("TEST FAILURE: forced worker error to validate UI failure path")

        with tempfile.TemporaryDirectory() as tmp:
            input_video = os.path.join(tmp, "input.mp4")
            clip_path = os.path.join(tmp, "clip.mp4")

            # 1) Download
            download_file(storage_url, input_video)

            # 2) Analyze
            _set_stage(STAGE_ANALYZING)
            duration = get_duration_seconds(input_video)
            print(f"[worker] Duration: {duration:.2f}s")

            cuts = detect_scene_timestamps(input_video, threshold=0.25)
            print(f"[worker] Scene cuts found: {len(cuts)}")

            if not cuts:
                fallback = 10.0 if duration > 12 else max(duration / 2, 0)
                cuts = [fallback]

            cut_time = cuts[0]
            _set_stage(STAGE_CUTTING, {"scene_time": float(cut_time)})

            # 3) Cut
            cut_clip(input_video, clip_path, cut_time, duration=4.0)

            # 4) Upload clip
            _set_stage(STAGE_UPLOADING)
            clip_storage_path = f"clips/{video_id}_clip1.mp4"
            clip_url = upload_video_file(clip_storage_path, clip_path)

            # ✅ Final meta + SSE
            _set_stage(
                STAGE_DONE,
                {
                    "status": STATUS_FINISHED,
                    "clip_url": clip_url,
                    "finished_at": _now(),
                },
            )

            # ✅ FINAL DB UPDATE (success)
            _db_update(
                effective_job_id,
                {
                    "status": "finished",
                    "stage": "done",
                    "clip_url": clip_url,
                    "error": None,
                    "error_reason": None,
                    "finished_at": _now(),
                },
            )

            # ✅ Day 13: charge credit ONLY after success (and only once)
            if effective_job_id and user_id:
                try:
                    charged = decrement_credit_if_not_charged(effective_job_id, user_id)
                    print(f"[worker] credit charged={charged} job_id={effective_job_id} user_id={user_id}")
                except Exception as e:
                    print(f"[worker] credit decrement failed for job_id={effective_job_id}: {e}")

            return {
                "video_id": video_id,
                "clip_url": clip_url,
                "scene_time": float(cut_time),
                "status": "ok",
            }

    except JobTimeoutException:
        reason = "Processing timed out (exceeded 10 minutes). Try a shorter video."
        print(f"[worker] TIMEOUT job_id={effective_job_id}: {reason}")

        j = get_current_job()
        if j:
            j.meta["status"] = STATUS_FAILED
            j.meta["stage"] = "timeout"
            j.meta["error_reason"] = reason
            j.meta["error"] = reason
            j.meta["finished_at"] = _now()
            j.save_meta()

            _publish(
                j.id,
                {
                    "status": "failed",
                    "stage": "timeout",
                    "error_reason": reason,
                    "error": reason,
                },
            )

        _db_update(
            effective_job_id,
            {
                "status": "failed",
                "stage": "timeout",
                "error_reason": reason,
                "error": reason,
                "finished_at": _now(),
            },
        )
        raise

    except Exception as e:
        reason = str(e).strip() or "Unknown processing error"
        trace = traceback.format_exc()
        print(f"[worker] ERROR job_id={effective_job_id}: {reason}\n{trace}")

        j = get_current_job()
        if j:
            j.meta["status"] = STATUS_FAILED
            j.meta["stage"] = "error"
            j.meta["error_reason"] = reason
            j.meta["error"] = reason
            j.meta["error_trace"] = trace[-1500:]
            j.meta["finished_at"] = _now()
            j.save_meta()

            _publish(
                j.id,
                {
                    "status": "failed",
                    "stage": "error",
                    "error_reason": reason,
                    "error": reason,
                },
            )

        _db_update(
            effective_job_id,
            {
                "status": "failed",
                "stage": "error",
                "error_reason": reason,
                "error": reason,
                "finished_at": _now(),
            },
        )

        raise
