from __future__ import annotations

from typing import Any, Dict, Optional, List
from app.services.supabase_client import get_supabase


def create_job(
    user_id: str,
    job_id: str,
    status: str,
    stage: str,
    source_video_url: Optional[str] = None,
) -> Dict[str, Any]:
    sb = get_supabase()
    payload = {
        "user_id": user_id,  # UUID string (matches DB uuid column)
        "job_id": job_id,
        "status": status,
        "stage": stage,
        "source_video_url": source_video_url,
    }
    res = sb.table("jobs").insert(payload).execute()
    return res.data[0]


def update_job(job_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker-friendly update (no user scope). Safe because it runs server-side.
    Routes should prefer update_job_for_user() if they ever update from an authenticated request.
    """
    sb = get_supabase()
    res = sb.table("jobs").update(fields).eq("job_id", job_id).execute()
    if not res.data:
        raise ValueError(f"Job not found for job_id={job_id}")
    return res.data[0]


def update_job_for_user(user_id: str, job_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Auth-safe update scoped to a specific user.
    """
    sb = get_supabase()
    res = (
        sb.table("jobs")
        .update(fields)
        .eq("job_id", job_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not res.data:
        raise ValueError(f"Job not found for user_id={user_id} job_id={job_id}")
    return res.data[0]


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Generic fetch by job_id (routes must enforce ownership; worker can use this).
    """
    sb = get_supabase()
    res = sb.table("jobs").select("*").eq("job_id", job_id).limit(1).execute()
    return res.data[0] if res.data else None


def get_job_for_user(user_id: str, job_id: str) -> Optional[Dict[str, Any]]:
    """
    Auth-safe fetch scoped to user.
    """
    sb = get_supabase()
    res = (
        sb.table("jobs")
        .select("*")
        .eq("job_id", job_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
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


# ✅ Day 14 helpers

def reset_job_for_retry(job_id: str) -> Dict[str, Any]:
    fields = {
        "status": "queued",
        "stage": "downloading",
        "error": None,
        "error_reason": None,
        "clip_url": None,
    }
    return update_job(job_id, fields)


def mark_job_failed(job_id: str, reason: str, stage: str = "error") -> Dict[str, Any]:
    fields = {
        "status": "failed",
        "stage": stage,
        "error": reason,
        "error_reason": reason,
    }
    return update_job(job_id, fields)
