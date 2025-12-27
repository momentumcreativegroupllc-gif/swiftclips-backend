from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    REDIS_URL: str = "redis://localhost:6379/0"

    # ✅ Day 15 auth verification config
    SUPABASE_PROJECT_URL: str
    SUPABASE_JWT_AUD: str = "authenticated"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ✅ prevents crashes if any extra env vars exist
    )

settings = Settings()
