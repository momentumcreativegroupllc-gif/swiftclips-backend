import os
import tempfile
import requests
from typing import Optional, Dict

from rq import get_current_job

from app.services.video_meta import get_duration_seconds
from app.services.scenes import detect_scene_timestamps
from app.services.clipper import cut_clip
from app.services.storage import upload_video_file
from app.repos.jobs_repo import update_job

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


def _set_stage(stage: str, extra: Optional[Dict] = None):
    job = get_current_job()
    if not job:
        return

    # Redis meta
    job.meta["stage"] = stage
    if extra:
        job.meta.update(extra)
    job.save_meta()

    # DB update
    fields = {"stage": stage}

    # Only force "processing" for non-final stages
    if stage not in (STAGE_DONE, "error"):
        fields["status"] = "processing"

    # Attach extra fields when present
    if extra and "clip_url" in extra:
        fields["clip_url"] = extra["clip_url"]
    if extra and "error" in extra:
        fields["error"] = extra["error"]

    try:
        update_job(job.id, fields)
    except Exception as e:
        print(f"[worker] DB update failed for job_id={job.id}: {e}")


def download_file(url: str, dst_path: str):
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dst_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def process_video_job(video_id: str, storage_url: str):
    job = get_current_job()
    if job:
        job.meta["status"] = STATUS_STARTED
        job.meta.pop("error", None)
        job.save_meta()

        # DB: mark as processing immediately
        try:
            update_job(
                job.id,
                {
                    "status": "processing",
                    "stage": STAGE_DOWNLOADING,
                    "error": None,
                },
            )
        except Exception as e:
            print(f"[worker] DB update failed on start for job_id={job.id}: {e}")

    try:
        _set_stage(STAGE_DOWNLOADING, {"video_id": video_id})
        print(f"[worker] started video_id={video_id}")

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
                print(f"[worker] No scene cuts found. Using fallback cut at {fallback:.2f}s")
                cuts = [fallback]

            cut_time = cuts[0]
            _set_stage(STAGE_CUTTING, {"scene_time": float(cut_time)})

            cut_clip(input_video, clip_path, cut_time, duration=4.0)

            _set_stage(STAGE_UPLOADING)
            clip_storage_path = f"clips/{video_id}_clip1.mp4"
            clip_url = upload_video_file(clip_storage_path, clip_path)

            # Redis meta: done
            _set_stage(STAGE_DONE, {"status": STATUS_FINISHED, "clip_url": clip_url})
            print(f"[worker] Clip uploaded: {clip_url}")

            # ✅ FINAL DB UPDATE (must be last write)
            if job:
                try:
                    update_job(
                        job.id,
                        {
                            "status": "finished",
                            "stage": "done",
                            "clip_url": clip_url,
                            "error": None,
                        },
                    )
                except Exception as e:
                    print(f"[worker] DB update failed on finish for job_id={job.id}: {e}")

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

            # DB: mark failed
            try:
                update_job(job.id, {"status": "failed", "stage": "error", "error": str(e)})
            except Exception as ex:
                print(f"[worker] DB update failed on error for job_id={job.id}: {ex}")

        raise
