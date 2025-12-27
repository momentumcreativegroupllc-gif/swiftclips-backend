# app/auth/supabase_jwt.py
import json
import os
import time
from typing import Dict, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

_user_cache: Dict[str, Any] = {"token": None, "payload": None, "ts": 0}

def verify_supabase_jwt(token: str, aud: str = "authenticated") -> Dict[str, Any]:
    """
    Validate a Supabase access token by asking Supabase Auth directly.
    This avoids JWKS/header issues and matches how Supabase validates sessions.

    Returns a dict containing at minimum {"sub": <user_id>, ...}
    """
    project_url = (os.getenv("SUPABASE_URL") or os.getenv("SUPABASE_PROJECT_URL") or "").strip()
    apikey = (os.getenv("SUPABASE_ANON_KEY") or "").strip()

    if not project_url:
        raise RuntimeError("SUPABASE_URL (recommended) or SUPABASE_PROJECT_URL not set")
    if not apikey:
        raise RuntimeError("SUPABASE_ANON_KEY not set")

    # small cache to reduce spam (10s)
    now = time.time()
    if _user_cache["token"] == token and _user_cache["payload"] and (now - _user_cache["ts"] < 10):
        return _user_cache["payload"]

    url = project_url.rstrip("/") + "/auth/v1/user"
    req = Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": apikey,
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body else {}

    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"Supabase /auth/v1/user returned {e.code}: {body or e.reason}")

    except URLError as e:
        raise RuntimeError(f"Supabase /auth/v1/user unreachable: {e}")

    # Supabase returns user object with "id"
    user_id = data.get("id")
    if not user_id:
        raise RuntimeError(f"Supabase /auth/v1/user missing id field: {data}")

    payload = {"sub": user_id, "aud": aud, "user": data}

    _user_cache["token"] = token
    _user_cache["payload"] = payload
    _user_cache["ts"] = now

    return payload
