from fastapi import APIRouter, Depends

from app.deps.auth import get_current_user_id
from app.repos.credits_repo import get_credits

router = APIRouter(tags=["me"])


@router.get("/me")
def me(user_id: str = Depends(get_current_user_id)):
    credits = get_credits(user_id)
    return {"user_id": user_id, "credits": credits}


@router.get("/credits")
def credits(user_id: str = Depends(get_current_user_id)):
    credits = get_credits(user_id)
    return {"credits": credits}
