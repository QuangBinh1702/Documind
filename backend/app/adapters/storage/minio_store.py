"""Lưu tệp gốc vào MinIO — US-006 AC-5.

Tên tệp trên kho là **UUID sinh mới**, không phải tên người dùng đặt
--------------------------------------------------------------------
Tên do người dùng kiểm soát mà dùng thẳng làm đường dẫn là lỗ hổng path
traversal kinh điển: `../../etc/passwd`, hay trên Windows là `..\\..\\`. Ngay cả
khi đã lọc, tên tệp còn mang theo hai vấn đề khác — trùng tên giữa hai người
dùng, và dấu tiếng Việt làm hỏng chữ ký của một số SDK.

Tên gốc vẫn được giữ, nhưng ở `sources.original_name` trong cơ sở dữ liệu, nơi
nó chỉ là dữ liệu chứ không phải đường dẫn.

Đường dẫn có dạng ``{user_id}/{notebook_id}/{uuid}{đuôi}``. Tiền tố theo người
dùng giúp truy vết và dọn dẹp; nó **không** phải cơ chế phân quyền — quyền vẫn
kiểm ở tầng SQL bằng INV-4.
"""

from __future__ import annotations

import io
import logging
import uuid
from functools import lru_cache

from app.settings import settings

__all__ = ["StorageError", "lay_tep", "luu_tep", "xoa_tep", "xoa_theo_tien_to"]

log = logging.getLogger(__name__)


class StorageError(Exception):
    """Kho tệp không dùng được."""


@lru_cache
def _client():
    try:
        from minio import Minio
    except ImportError as exc:  # pragma: no cover - phụ thuộc môi trường
        raise StorageError("Thiếu thư viện minio trên máy chủ.") from exc

    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def _bucket() -> str:
    client = _client()
    try:
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
    except Exception as exc:
        raise StorageError(f"Không kết nối được kho tệp: {exc}") from exc
    return settings.minio_bucket


def luu_tep(
    data: bytes,
    *,
    user_id: uuid.UUID,
    notebook_id: uuid.UUID,
    suffix: str,
    content_type: str,
) -> str:
    """Ghi tệp và trả về khoá lưu trữ."""
    key = f"{user_id}/{notebook_id}/{uuid.uuid4().hex}{suffix.lower()}"
    try:
        _client().put_object(
            _bucket(), key, io.BytesIO(data), length=len(data),
            content_type=content_type,
        )
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError(f"Không ghi được tệp vào kho: {exc}") from exc

    log.info("Đã lưu %s (%d byte)", key, len(data))
    return key


def lay_tep(key: str) -> bytes:
    resp = None
    try:
        resp = _client().get_object(_bucket(), key)
        return resp.read()
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError(f"Không đọc được tệp {key}: {exc}") from exc
    finally:
        if resp is not None:
            resp.close()
            resp.release_conn()


def xoa_tep(key: str) -> None:
    """Xoá một tệp. Tệp không còn ở đó cũng coi như xong."""
    try:
        _client().remove_object(_bucket(), key)
    except Exception as exc:
        log.warning("Không xoá được %s: %s", key, exc)


def xoa_theo_tien_to(prefix: str) -> int:
    """Xoá mọi tệp dưới một tiền tố — dùng khi xoá notebook (US-005 AC-4)."""
    try:
        client = _client()
        bucket = _bucket()
        keys = [o.object_name for o in client.list_objects(bucket, prefix=prefix,
                                                           recursive=True)]
        for k in keys:
            client.remove_object(bucket, k)
        return len(keys)
    except Exception as exc:
        log.warning("Không dọn được tiền tố %s: %s", prefix, exc)
        return 0
