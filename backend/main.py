"""
AI Shorts Generator - FastAPI Backend
"""
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.api.routes import router
from backend.config import OUTPUT_DIR

app = FastAPI(
    title="AI Shorts Generator",
    description="AI 기반 쇼츠 영상 자동 생성 API",
    version="1.0.0",
)

# CORS - allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes first (before static mounts)
app.include_router(router)

# Mount output directory for video serving
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

# Frontend directory
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/")
async def serve_frontend():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/ssul_shorts")
@app.get("/ssul_shorts/")
async def serve_ssul_shorts():
    return FileResponse(str(FRONTEND_DIR / "ssul_shorts" / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}


# Mount frontend static files (CSS, JS) - must be last
# Enabled html=True to naturally serve subdirectory index.html files
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
