from fastapi import FastAPI

from app.api.routes_upload import router as upload_router

app = FastAPI(title="SwiftClips API")

@app.get("/")
async def root():
    return {"status": "ok", "service": "swiftclips"}

app.include_router(upload_router)
