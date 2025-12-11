from fastapi import APIRouter, UploadFile, File, HTTPException
import uuid

from app.services.storage import upload_video_bytes
from app.services.queue import queue
from app.workers.video_jobs import process_video_job

router = APIRouter(prefix="/upload", tags=["upload"])

@router.post("/video")
async def upload_video(file: UploadFile = File(...)):
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Must be a video.")

    # Create a unique file path
    ext = file.filename.split(".")[-1]
    video_id = str(uuid.uuid4())
    path = f"raw/{video_id}.{ext}"

    # Read uploaded file bytes
    data = await file.read()

    # Upload to Supabase
    url = upload_video_bytes(path, data)

    # Enqueue background job
    job = queue.enqueue(process_video_job, video_id, url)

    return {
        "video_id": video_id,
        "storage_url": url,
        "job_id": job.id,
        "status": "queued"
    }
