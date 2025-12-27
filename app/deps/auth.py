from typing import Optional

import os
from fastapi import Header, HTTPException, Query

from app.auth.supabase_jwt import verify_supabase_jwt

AUD = os.getenv("SUPABASE_JWT_AUD", "authenticated")


def get_current_user_id(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),  # SSE fallback: /events?token=...
) -> str:
    bearer: Optional[str] = None

    if authorization and authorization.startswith("Bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
    elif token:
        bearer = token.strip()

    if not bearer:
        raise HTTPException(status_code=401, detail="Missing auth token")

    try:
        # Support BOTH verifier signatures:
        # - old: verify_supabase_jwt(token, aud="authenticated")
        # - new: verify_supabase_jwt(token, audiences=("authenticated","anon"), issuer=...)
        try:
            payload = verify_supabase_jwt(bearer, audiences=(AUD,))
        except TypeError:
            payload = verify_supabase_jwt(bearer, aud=AUD)

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="JWT missing sub")
        return str(user_id)
    except HTTPException:
        raise
    except Exception as e:
        # Helpful debug while building. You can reduce later.
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {str(e)}")
