# app/repos/credits_repo.py
from __future__ import annotations

from app.services.supabase_client import get_supabase

CREDITS_DEFAULT = 3


def get_credits(user_id: str) -> int:
    """
    Returns current credits for user. If user has no row yet, create it with default credits.
    """
    sb = get_supabase()

    res = (
        sb.table("user_credits")
        .select("credits")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )

    if res.data and res.data.get("credits") is not None:
        return int(res.data["credits"])

    sb.table("user_credits").insert(
        {"user_id": user_id, "credits": CREDITS_DEFAULT}
    ).execute()

    return CREDITS_DEFAULT


def set_credits(user_id: str, credits: int) -> None:
    sb = get_supabase()
    sb.table("user_credits").upsert(
        {"user_id": user_id, "credits": credits}
    ).execute()


def decrement_credit_if_not_charged(job_id: str, user_id: str) -> bool:
    """
    Deduct 1 credit only if this job has NOT been charged yet.
    job_id here is the RQ job id (stored in public.jobs.job_id text).
    Returns True if we deducted, False if already charged or job not found.
    """
    sb = get_supabase()

    # ✅ IMPORTANT: match on jobs.job_id (text), NOT jobs.id (uuid)
    job_res = (
        sb.table("jobs")
        .select("job_id, credit_charged")
        .eq("job_id", job_id)
        .maybe_single()
        .execute()
    )

    if not job_res.data:
        # job row missing -> don't charge
        print(f"[credits_repo] job not found for job_id={job_id}")
        return False

    if job_res.data.get("credit_charged") is True:
        return False

    credits = get_credits(user_id)
    new_credits = max(int(credits) - 1, 0)

    # update credits
    sb.table("user_credits").update(
        {"credits": new_credits}
    ).eq("user_id", user_id).execute()

    # mark job as charged
    sb.table("jobs").update(
        {"credit_charged": True}
    ).eq("job_id", job_id).execute()

    return True
