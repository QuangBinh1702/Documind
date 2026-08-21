"""Điểm vào của dịch vụ API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.settings import settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)
log = logging.getLogger("documind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("DocuMind khởi động · env=%s · device=%s", settings.app_env, settings.device)
    for w in settings.warnings():
        log.warning("Cấu hình: %s", w)
    yield
    log.info("DocuMind dừng")


app = FastAPI(
    title="DocuMind API",
    description="Nền tảng hỏi đáp tài liệu có trích dẫn nguồn",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Chỉ mở cho frontend cục bộ. Siết lại khi triển khai thật.
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
