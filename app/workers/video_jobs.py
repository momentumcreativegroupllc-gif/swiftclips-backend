import os
import tempfile
import requests
from typing import Optional, Dict

from rq import get_current_job

from app.services.progress_pubsub import safe_publish
from app.services.video_meta import get_duration_seconds
from app.services.scenes import detect_scene_timestamps
from app.services.clipper import cut_clip
from app.services.storage import upload_video_file
from app.repos.jobs_repo import update_job

from app.repos.credits_repo import decrement_credit_if_not_charged  # ✅ Day 13
from app.services.supabase_client import get_supabase  # ✅ Day 13 (used to fetch user_id)

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


def _set_stage(stage: str, extra: Optional[Dict] = None) -> None:
    """
    Update RQ job meta + publish real-time progress event for SSE.
    """
    job = get_current_job()
    if not job:
        return

    job.meta["stage"] = stage

    # Respect caller status if present, otherwise default to processing
    if extra and "status" in extra:
        job.meta["status"] = extra["status"]
    else:
        job.meta["status"] = "processing"

    if extra:
        job.meta.update(extra)

    job.save_meta()

    safe_publish(
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


def process_video_job(video_id: str, storage_url: str, job_id: Optional[str] = None):
    """
    NOTE:
    - RQ job.id is the enqueue job_id we set in upload route (string UUID)
    - DB jobs table has:
        id (uuid) primary key
        job_id (text)  <-- this is what matches RQ job.id / job_id
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
                .eq("job_id", effective_job_id)  # ✅ IMPORTANT: job_id (text), NOT id (uuid)
                .single()
                .execute()
            )
            user_id = db_job.data.get("user_id")
        except Exception as e:
            print(f"[worker] Failed to fetch user_id for job_id={effective_job_id}: {e}")

    # Mark started in meta + DB
    if job:
        job.meta["status"] = STATUS_STARTED
        job.meta.pop("error", None)
        job.save_meta()

    if effective_job_id:
        try:
            update_job(
                effective_job_id,
                {
                    "status": "processing",
                    "stage": STAGE_DOWNLOADING,
                    "error": None,
                },
            )
        except Exception as e:
            print(f"[worker] DB update failed on start for job_id={effective_job_id}: {e}")

    try:
        _set_stage(STAGE_DOWNLOADING, {"video_id": video_id})
        print(f"[worker] started video_id={video_id} job_id={effective_job_id}")

        with tempfile.TemporaryDirectory() as tmp:
            input_video = os.path.join(tmp, "input.mp4")
            clip_path = os.path.join(tmp, "clip.mp4")

            download_file(storage_url, input_video)

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

            cut_clip(input_video, clip_path, cut_time, duration=4.0)

            _set_stage(STAGE_UPLOADING)
            clip_storage_path = f"clips/{video_id}_clip1.mp4"
            clip_url = upload_video_file(clip_storage_path, clip_path)

            # ✅ Final meta + SSE
            _set_stage(
                STAGE_DONE,
                {
                    "status": STATUS_FINISHED,
                    "clip_url": clip_url,
                },
            )

            # ✅ FINAL DB UPDATE (success)
            if effective_job_id:
                try:
                    update_job(
                        effective_job_id,
                        {
                            "status": "finished",
                            "stage": "done",
                            "clip_url": clip_url,
                            "error": None,
                        },
                    )
                except Exception as e:
                    print(f"[worker] DB update failed on finish for job_id={effective_job_id}: {e}")

                # ✅ Day 13: charge credit ONLY after success (and only once)
                if user_id:
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

    except Exception as e:
        job = get_current_job()

        if job:
            job.meta["status"] = STATUS_FAILED
            job.meta["error"] = str(e)
            job.save_meta()

        safe_publish(
            job.id if job else None,
            {
                "status": "failed",
                "stage": "error",
                "error": str(e),
            },
        )

        # ❌ NO CREDIT DEDUCTION HERE (by design)
        if effective_job_id:
            try:
                update_job(
                    effective_job_id,
                    {
                        "status": "failed",
                        "stage": "error",
                        "error": str(e),
                    },
                )
            except Exception as ex:
                print(f"[worker] DB update failed on error for job_id={effective_job_id}: {ex}")

        raise
