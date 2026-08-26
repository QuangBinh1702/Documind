"""Điểm vào của dịch vụ API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, config, health, notebooks, share, stats
from app.settings import settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)
log = logging.getLogger("documind")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("DocuMind khởi động · env=%s · device=%s", settings.app_env, settings.device)
    loi = settings.loi_chan_khoi_dong()
    if loi:
        for dong in loi:
            log.critical("Cấu hình production không hợp lệ: %s", dong)
        raise RuntimeError(
            "Từ chối khởi động ở production với cấu hình mẫu: " + " · ".join(loi)
        )
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
    # Mặc định chỉ mở cho frontend cục bộ; đặt CORS_ORIGINS khi triển khai thật.
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Trình duyệt chỉ đọc được header "đơn giản" của phản hồi khác origin.
    # Không khai báo dòng này thì `taiVe()` ở giao diện không thấy tên tệp
    # máy chủ đặt và mọi bản xuất tải về đều mang tên dự phòng.
    expose_headers=["Content-Disposition", "Retry-After"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(notebooks.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(share.router, prefix="/api")


@app.get("/", include_in_schema=False)
def goc() -> dict[str, str]:
    """Gốc của dịch vụ API.

    Trước đây đây là "bàn thử": một trang HTML tĩnh gọi thẳng các endpoint hội
    thoại khi chúng còn chưa đòi đăng nhập. Giao diện Next.js đã thay thế nó
    hoàn toàn, và các endpoint ấy giờ đòi token — nên trang bàn thử không những
    thừa mà còn không chạy được nữa.
    """
    return {"service": "documind", "docs": "/api/docs", "health": "/api/health"}
