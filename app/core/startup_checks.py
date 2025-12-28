from __future__ import annotations

import sys
from typing import List

import redis

from app.core.config import settings


def _missing_env(required: List[str]) -> List[str]:
    missing = []
    for k in required:
        v = getattr(settings, k, None)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(k)
    return missing


def run_startup_checks() -> None:
    # 1) Required env vars (fail fast)
    required = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_PROJECT_URL",
        "REDIS_URL",
        "QUEUE_NAME",
    ]
    missing = _missing_env(required)
    if missing:
        print("\n❌ Startup check failed: missing required env vars:", file=sys.stderr)
        for k in missing:
            print(f"   - {k}", file=sys.stderr)
        print("\nFix: add them to .env (backend repo root) and restart.\n", file=sys.stderr)
        raise SystemExit(1)

    # 2) Redis connectivity
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
    except Exception as e:
        print("\n❌ Startup check failed: cannot connect to Redis", file=sys.stderr)
        print(f"   REDIS_URL={settings.REDIS_URL}", file=sys.stderr)
        print(f"   error={e}", file=sys.stderr)
        print("\nFix: ensure Redis is running / URL is correct.\n", file=sys.stderr)
        raise SystemExit(1)

    # 3) Supabase sanity check (no network call required here, just basic validation)
    # We avoid making a real DB call at startup to keep boot fast.
    # But we do ensure URLs look valid.
    if not settings.SUPABASE_URL.startswith("https://"):
        print("\n❌ Startup check failed: SUPABASE_URL must start with https://", file=sys.stderr)
        print(f"   SUPABASE_URL={settings.SUPABASE_URL}", file=sys.stderr)
        raise SystemExit(1)

    print("✅ Startup checks passed")
