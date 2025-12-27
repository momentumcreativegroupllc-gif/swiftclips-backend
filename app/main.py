from pathlib import Path
from dotenv import load_dotenv

# Always load repo-root .env (NOT dependent on current working directory)
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"  # .../swiftclips-backend/.env
load_dotenv(dotenv_path=ENV_PATH, override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_upload import router as upload_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_me import router as me_router

app = FastAPI(title="SwiftClips API")

# ✅ CORS: allow Next dev server on 3000 or 3001, localhost or 127.0.0.1
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "ok", "service": "swiftclips"}

app.include_router(upload_router)
app.include_router(jobs_router)
app.include_router(me_router)
