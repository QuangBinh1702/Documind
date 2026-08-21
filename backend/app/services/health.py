"""Dò trạng thái các thành phần phụ thuộc.

Mỗi phép dò tự bắt lỗi của mình. Một thành phần chết không được làm sập cả
endpoint — nếu không thì health check trở nên vô dụng đúng lúc cần nó nhất.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from app.schemas.health import ComponentHealth, HealthResponse
from app.settings import settings

# Không để một thành phần treo làm treo cả endpoint.
PROBE_TIMEOUT_S = 3.0


def _timed(fn: Callable[[], None]) -> ComponentHealth:
    start = time.perf_counter()
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 — health check phải bắt hết
        return ComponentHealth(
            status="down",
            detail=f"{type(exc).__name__}: {exc}"[:200],
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    return ComponentHealth(
        status="ok",
        latency_ms=int((time.perf_counter() - start) * 1000),
    )


def _probe_postgres() -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            # Không chỉ kiểm tra kết nối — kiểm tra cả những thứ hệ thống
            # thực sự phụ thuộc, để lỗi lộ ra ở đây thay vì ở lúc index.
            conn.execute(text("SELECT '[1,2,3]'::vector"))
            conn.execute(text("SELECT to_tsvector('vi', 'cơ_sở_dữ_liệu')"))
    finally:
        engine.dispose()


def _probe_redis() -> None:
    import redis

    client = redis.from_url(settings.redis_url, socket_connect_timeout=PROBE_TIMEOUT_S)
    try:
        client.ping()
    finally:
        client.close()


def _probe_minio() -> None:
    from minio import Minio

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    if not client.bucket_exists(settings.minio_bucket):
        raise RuntimeError(f"Bucket '{settings.minio_bucket}' chưa tồn tại")


def _probe_gpu() -> ComponentHealth:
    """Trên máy phát triển DEVICE=cpu, đây không phải lỗi — là lựa chọn."""
    if settings.device != "cuda":
        return ComponentHealth(status="skipped", detail="DEVICE=cpu")
    try:
        import torch

        if not torch.cuda.is_available():
            return ComponentHealth(status="down", detail="torch không thấy CUDA")
        name = torch.cuda.get_device_name(0)
        total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        used_gb = torch.cuda.memory_reserved(0) / 1024**3
        return ComponentHealth(
            status="ok",
            detail=f"{name} — {used_gb:.1f}/{total_gb:.1f} GB",
        )
    except Exception as exc:  # noqa: BLE001
        return ComponentHealth(status="down", detail=f"{type(exc).__name__}: {exc}"[:200])


async def collect_health() -> HealthResponse:
    loop = asyncio.get_running_loop()

    async def run(fn: Callable[[], None]) -> ComponentHealth:
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, _timed, fn), timeout=PROBE_TIMEOUT_S
            )
        except TimeoutError:
            return ComponentHealth(
                status="down", detail=f"quá {PROBE_TIMEOUT_S:.0f}s không phản hồi"
            )

    postgres, redis_health, minio = await asyncio.gather(
        run(_probe_postgres), run(_probe_redis), run(_probe_minio)
    )
    components = {
        "postgres": postgres,
        "redis": redis_health,
        "minio": minio,
        "gpu": _probe_gpu(),
    }

    # 'skipped' không phải lỗi — chỉ 'down' mới làm hệ thống degraded.
    healthy = all(c.status != "down" for c in components.values())

    return HealthResponse(
        status="ok" if healthy else "degraded",
        app_env=settings.app_env,
        device=settings.device,
        components=components,
        warnings=settings.warnings(),
    )
