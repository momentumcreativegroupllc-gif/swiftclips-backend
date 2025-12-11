from supabase import create_client, Client
from app.core.config import settings

# Use the service role key on the backend so we bypass RLS for storage
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

BUCKET_NAME = "videos"

def upload_video_bytes(path: str, data: bytes) -> str:
    """
    Upload raw bytes to Supabase Storage and return a public URL.
    """
    result = supabase.storage.from_(BUCKET_NAME).upload(path, data)
    public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(path)
    return public_url
