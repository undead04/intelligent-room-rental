"""Entrypoint khởi chạy Uvicorn cho Homigo AI Agent (tách biệt hoàn toàn khỏi logic service)."""

from __future__ import annotations

import os
import uvicorn

from api.routes import app

__all__ = ["app"]

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8001"))
    reload = os.getenv("ENV", "development").lower() == "development"
    uvicorn.run("main:app", host=host, port=port, reload=reload)
