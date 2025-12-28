from __future__ import annotations

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Required core deps ---
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    REDIS_URL: str  # Day 16: must be provided via env
    QUEUE_NAME: str = "swiftclips"  # safe default (not localhost-specific)

    # --- Day 15 auth verification config ---
    SUPABASE_PROJECT_URL: str
    SUPABASE_JWT_AUD: str = "authenticated"

    # --- Day 16: CORS ---
    # Comma-separated list, e.g.:
    # CORS_ORIGINS="http://localhost:3000,http://localhost:3001,https://your-frontend.vercel.app"
    CORS_ORIGINS: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def cors_origins_list(self) -> List[str]:
        """
        Returns an origins list for FastAPI CORSMiddleware.
        - If CORS_ORIGINS env is set, use it.
        - Else default to local dev origins.
        """
        if self.CORS_ORIGINS:
            parts = [p.strip() for p in self.CORS_ORIGINS.split(",")]
            return [p for p in parts if p]

        # Dev-friendly fallback only when not configured
        return [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
        ]


settings = Settings()
