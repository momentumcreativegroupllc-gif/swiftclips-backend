from __future__ import annotations
from typing import Any, Dict, Optional, List
from app.services.supabase_client import get_supabase

DEMO_USER_ID = "demo"

def create_job(
    user_id: str,
    job_id: str,
    status: str,
    stage: str,
    source_video_url: Optional[str] = None,
) -> Dict[str, Any]:
    sb = get_supabase()
    payload = {
        "user_id": user_id,
        "job_id": job_id,
        "status": status,
        "stage": stage,
        "source_video_url": source_video_url,
    }
    res = sb.table("jobs").insert(payload).execute()
    return res.data[0]

def update_job(job_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    sb = get_supabase()
    res = sb.table("jobs").update(fields).eq("job_id", job_id).execute()
    if not res.data:
        raise ValueError(f"Job not found for job_id={job_id}")
    return res.data[0]

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    sb = get_supabase()
    res = sb.table("jobs").select("*").eq("job_id", job_id).limit(1).execute()
    return res.data[0] if res.data else None

def list_jobs(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    sb = get_supabase()
    res = (
        sb.table("jobs")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []
