import logging
import os
logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from finance_api import router as finance_router
from finance_db import init_db

app = FastAPI(title="Finance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
app.include_router(finance_router)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/manifest.json")
    def manifest():
        return FileResponse(os.path.join(STATIC_DIR, "manifest.json"))

    @app.get("/apple-touch-icon.png")
    def touch_icon():
        return FileResponse(os.path.join(STATIC_DIR, "apple-touch-icon.png"))

    @app.get("/icon-192.png")
    def icon192():
        return FileResponse(os.path.join(STATIC_DIR, "icon-192.png"))

    @app.get("/icon-512.png")
    def icon512():
        return FileResponse(os.path.join(STATIC_DIR, "icon-512.png"))
else:
    @app.get("/")
    def health():
        return {"status": "ok"}
