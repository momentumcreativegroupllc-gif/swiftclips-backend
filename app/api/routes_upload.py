from fastapi import APIRouter, UploadFile, File, HTTPException
import uuid
import tempfile
import os

from storage3.exceptions import StorageApiError

from app.repos.jobs_repo import create_job, DEMO_USER_ID
from app.repos.credits_repo import get_credits  # ✅ Day 13: credit gate
from app.services.storage import upload_video_file
from app.services.queue import queue

router = APIRouter(prefix="/upload", tags=["upload"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB MVP cap


@router.post("/video")
async def upload_video(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Must be a video.")

    # ✅ Day 13: Block upload if user has 0 credits (gate BEFORE job creation/enqueue)
    credits = get_credits(DEMO_USER_ID)
    if credits <= 0:
        raise HTTPException(status_code=402, detail="No credits remaining. Upload blocked.")

    video_id = str(uuid.uuid4())
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "mp4"
    storage_path = f"raw/{video_id}.{ext}"

    bytes_written = 0
    tmp_path = None

    try:
        # 1) Save upload to a temp file (streaming)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    tmp.close()
                    raise HTTPException(status_code=413, detail="File too large for MVP. Max upload size is 50MB.")
                tmp.write(chunk)

        # 2) Upload temp file to storage (Supabase)
        try:
            url = upload_video_file(storage_path, tmp_path)
        except StorageApiError as e:
            msg = str(e)
            if "413" in msg or "Payload too large" in msg or "maximum allowed size" in msg:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        "Upload rejected by storage provider: file exceeds Supabase max object size. "
                        "For now upload a smaller file."
                    ),
                )
            raise

        # 3) Generate our own job_id so DB row + RQ job always match
        job_id = str(uuid.uuid4())

        # 4) Create DB job row immediately (queued/downloading)
        create_job(
            user_id=DEMO_USER_ID,
            job_id=job_id,
            status="queued",
            stage="downloading",
            source_video_url=url,
        )

        # 5) Enqueue job in Redis for the worker
        queue.enqueue(
            "app.workers.video_jobs.process_video_job",
            video_id,
            url,
            job_id=job_id,
        )

        # 6) Return immediately (frontend gets job_id, can connect SSE)
        return {"job_id": job_id, "video_id": video_id, "storage_url": url, "status": "queued"}

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
