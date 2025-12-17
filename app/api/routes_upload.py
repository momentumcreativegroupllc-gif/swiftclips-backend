from fastapi import APIRouter, UploadFile, File, HTTPException
import uuid
import tempfile
import os

from storage3.exceptions import StorageApiError
from app.repos.jobs_repo import create_job, DEMO_USER_ID
from app.services.storage import upload_video_file
from app.services.queue import queue
from app.workers.video_jobs import process_video_job

router = APIRouter(prefix="/upload", tags=["upload"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 200MB MVP cap (app-side)

@router.post("/video")
async def upload_video(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Must be a video.")

    video_id = str(uuid.uuid4())
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "mp4"
    storage_path = f"raw/{video_id}.{ext}"

    bytes_written = 0

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
        while True:
            chunk = await file.read(1024 * 1024)  # 1MB
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_BYTES:
                tmp.close()
                os.remove(tmp_path)
                raise HTTPException(status_code=413, detail="File too large for MVP. Max upload size is 50MB.")
            tmp.write(chunk)

    try:
        try:
            url = upload_video_file(storage_path, tmp_path)
        except StorageApiError as e:
            # Supabase Storage rejecting large objects (provider-side limit)
            msg = str(e)
            if "413" in msg or "Payload too large" in msg or "maximum allowed size" in msg:
                raise HTTPException(
                    status_code=413,
                    detail="Upload rejected by storage provider: file exceeds Supabase max object size. For now upload a smaller file (we'll support 200MB after adjusting storage)."
                )
            raise

        job = queue.enqueue(process_video_job, video_id, url)
        create_job(
    user_id=DEMO_USER_ID,
    job_id=job.id,
    status="queued",
    stage="downloading",
    source_video_url=url,
)
        
        return {"job_id": job.id, "video_id": video_id, "storage_url": url, "status": "queued"}

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
