from supabase import create_client
from app.core.config import settings

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
BUCKET = "videos"

def upload_video_file(path: str, file_path: str, content_type: str = "video/mp4") -> str:
    with open(file_path, "rb") as f:
        data = f.read()
    supabase.storage.from_(BUCKET).upload(path, data, {"content-type": content_type})
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"
