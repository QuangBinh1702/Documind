"""Hàng đợi xử lý tài liệu — US-021.

Vì sao cần hàng đợi thật, không chỉ `BackgroundTasks`
------------------------------------------------------
`BackgroundTasks` của FastAPI chạy công việc trong **chính tiến trình API**, sau
khi response đã gửi. Nó đủ tốt để phát triển, nhưng nó hỏng ở ba chỗ mà US-021
nêu đích danh:

* Khởi động lại API — kể cả khi sửa một dòng mã ở chế độ `--reload` — là mất
  toàn bộ việc đang chạy dở. Tài liệu kẹt ở `parsing` mãi mãi.
* Nạp một tài liệu chiếm một luồng của API suốt hàng chục giây. Vài tệp cùng
  lúc là API hết luồng để trả lời câu hỏi.
* Không có cách nào giới hạn số việc chạy song song. Hai tài liệu cùng nhúng
  trên GPU 16 GB là tràn VRAM (AC-3).

Celery tách việc ra một tiến trình khác, và `--concurrency=1` biến hàng đợi
thành **tuần tự** — đúng thứ cần khi tài nguyên hiếm là GPU chứ không phải CPU.

Xác nhận muộn, không lấy trước
-------------------------------
`task_acks_late=True` giữ việc trong hàng đợi cho tới khi nó **xong**, nên
worker chết giữa chừng thì việc được giao lại chứ không biến mất.
`worker_prefetch_multiplier=1` chặn worker ôm sẵn việc thứ hai: với việc kéo dài
hàng phút, ôm trước chỉ làm chúng nằm chờ ở một worker đang bận trong khi một
worker khác rảnh.
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.signals import worker_ready

from app.settings import settings

__all__ = ["celery_app", "xu_ly_nguon_task"]

log = logging.getLogger(__name__)

celery_app = Celery(
    "documind",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    # Trần cứng cho một tài liệu. OCR 500 trang trên CPU có thể chạm ngưỡng này;
    # khi đó việc bị giết và ghi `failed` kèm lý do, thay vì treo vô hạn và giữ
    # chỗ của mọi tài liệu xếp sau.
    task_time_limit=settings.task_time_limit_seconds,
    task_soft_time_limit=settings.task_time_limit_seconds - 60,
    timezone="UTC",
    enable_utc=True,
    # Kết quả chỉ dùng để gỡ lỗi; trạng thái thật nằm ở `sources.status`.
    result_expires=3600,
)


@celery_app.task(name="documind.xu_ly_nguon", bind=True)
def xu_ly_nguon_task(self, source_id: str) -> None:
    """Bọc `xu_ly_nguon` thành một task.

    Thân xử lý nằm ở `app.workers.tasks` và **không biết gì về Celery** — nhờ
    vậy CLI, test và đường `BackgroundTasks` đều gọi được cùng một mã.
    """
    from app.workers.tasks import xu_ly_nguon

    log.info("Nhận việc xử lý nguồn %s (task %s)", source_id, self.request.id)
    xu_ly_nguon(source_id)


@worker_ready.connect
def don_viec_do_dang(**_: object) -> None:
    """AC-4 — việc dở dang lúc worker chết phải được kết luận, không kẹt.

    Worker bị giết giữa chừng để lại những hàng `sources` ở trạng thái
    `parsing`, `ocr`, `chunking` hay `embedding`. Không ai dọn thì chúng nằm đó
    mãi: giao diện hiện "đang xử lý" vĩnh viễn, người dùng chờ một việc đã chết.

    Dọn lúc worker **khởi động** chứ không lúc nó tắt: worker bị `kill -9` hoặc
    máy mất điện thì không có lúc tắt nào để chạy mã dọn.

    Chạy được vì `--concurrency=1` và mỗi máy chỉ có một worker: mọi việc đang
    dở khi worker này khởi động đều là tàn dư của lần chạy trước. Với nhiều
    worker song song thì cần thêm cột ghi worker nào đang giữ việc nào.
    """
    from sqlalchemy import update

    from app.models.base import session_scope
    from app.models.knowledge import Source

    DANG_CHAY = ("parsing", "ocr", "chunking", "embedding")

    try:
        with session_scope() as s:
            ket_qua = s.execute(
                update(Source)
                .where(Source.status.in_(DANG_CHAY))
                .values(
                    status="failed",
                    progress=100,
                    error_code="WORKER_RESTARTED",
                    error_message=(
                        "Quá trình xử lý bị gián đoạn do máy chủ khởi động lại. "
                        "Hãy xoá tài liệu này và tải lên lại."
                    ),
                )
            )
        if ket_qua.rowcount:
            log.warning(
                "Đánh dấu %d tài liệu dở dang là failed sau khi worker khởi động lại",
                ket_qua.rowcount,
            )
    except Exception as exc:  # pragma: no cover - chỉ chạy khi có DB thật
        # Không chặn worker khởi động vì một bước dọn dẹp. Việc mới vẫn chạy
        # được; chỉ là tài liệu cũ còn kẹt cho tới lần khởi động sau.
        log.error("Không dọn được việc dở dang: %s", exc)
