"""Tiến độ xử lý tài liệu theo thời gian thực — US-022.

Vì sao qua Redis chứ không ghi thẳng vào `sources`
--------------------------------------------------
`ingest_file` chạy trong **một transaction dài**: từ lúc trích xuất tới lúc ghi
chunk là một khối. Mọi thay đổi nó ghi vào hàng `sources` chỉ hiện ra với người
khác khi transaction đó commit — tức là khi đã xong. Một thanh tiến trình chỉ
nhảy lên 100% ở cuối thì không phải thanh tiến trình.

Cách sửa "hiển nhiên" — mở một phiên ngắn khác để cập nhật — lại **treo**: hàng
`sources` đang bị transaction dài khoá ghi, nên câu UPDATE thứ hai nằm chờ chính
transaction mà nó đang muốn báo tiến độ.

Redis nằm ngoài transaction đó nên không có xung đột nào. Nó cũng chịu được nhịp
ghi dày: OCR một tài liệu 500 trang phát 500 lượt cập nhật, và ngần ấy lượt
UPDATE vào Postgres là lãng phí cho một dữ liệu sống vài phút rồi bỏ.

Hỏng thì im lặng bỏ qua
------------------------
Redis chết thì tiến độ chi tiết biến mất, nhưng việc xử lý tài liệu vẫn chạy và
trạng thái thô (`queued` → `parsing` → `ready`) vẫn nằm trong `sources`. Đánh
đổi đúng chiều: không ai muốn mất tài liệu chỉ vì mất thanh tiến trình.
"""

from __future__ import annotations

import json
import logging
import uuid

from app.settings import settings

__all__ = ["TienDo", "dat", "doc", "xoa"]

log = logging.getLogger(__name__)

_KHOA = "documind:progress:{source_id}"

# Sống đủ lâu cho một lượt xử lý dài, ngắn đủ để không tích rác.
_TTL_GIAY = 3600


class TienDo(dict):
    """`{"status": ..., "progress": int, "message": str}` — chỉ là dict có tên."""


def _redis():
    try:
        import redis

        return redis.from_url(settings.redis_url, socket_connect_timeout=2)
    except Exception as exc:
        log.debug("Không dùng được Redis cho tiến độ: %s", exc)
        return None


def dat(source_id: uuid.UUID | str, *, status: str, progress: int, message: str = "") -> None:
    """Ghi lại tiến độ hiện tại của một nguồn."""
    r = _redis()
    if r is None:
        return
    try:
        r.setex(
            _KHOA.format(source_id=source_id),
            _TTL_GIAY,
            json.dumps(
                {"status": status, "progress": max(0, min(100, progress)),
                 "message": message},
                ensure_ascii=False,
            ),
        )
    except Exception as exc:
        log.debug("Không ghi được tiến độ của %s: %s", source_id, exc)
    finally:
        r.close()


def doc(source_ids: list[uuid.UUID]) -> dict[str, TienDo]:
    """Tiến độ của nhiều nguồn cùng lúc. Nguồn không có bản ghi thì vắng mặt.

    Đọc theo lô bằng `MGET`: endpoint SSE gọi hàm này mỗi giây cho cả danh sách
    nguồn, và một lượt đi mạng cho mỗi nguồn sẽ nhân lên rất nhanh.
    """
    if not source_ids:
        return {}

    r = _redis()
    if r is None:
        return {}
    try:
        khoa = [_KHOA.format(source_id=s) for s in source_ids]
        ket: dict[str, TienDo] = {}
        for sid, raw in zip(source_ids, r.mget(khoa), strict=True):
            if raw:
                ket[str(sid)] = TienDo(json.loads(raw))
        return ket
    except Exception as exc:
        log.debug("Không đọc được tiến độ: %s", exc)
        return {}
    finally:
        r.close()


def xoa(source_id: uuid.UUID | str) -> None:
    r = _redis()
    if r is None:
        return
    try:
        r.delete(_KHOA.format(source_id=source_id))
    except Exception as exc:
        log.debug("Không xoá được tiến độ của %s: %s", source_id, exc)
    finally:
        r.close()
