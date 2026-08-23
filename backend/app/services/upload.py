"""Nhận một tệp tải lên và đưa vào hàng đợi xử lý — US-006.

Kiểm tra theo thứ tự **rẻ trước, đắt sau**, và mỗi bước từ chối sớm nhất có thể:

1. Đuôi tệp có được hỗ trợ không          (AC-2) — chỉ đọc tên
2. Notebook đã đầy chưa                    (AC-4) — một câu đếm
3. Kích thước có vượt hạn mức không        (AC-3) — không đọc hết dữ liệu
4. Nội dung có đúng là định dạng đó không  (AC-5) — đọc vài byte đầu

Bước 4 là bước không thể bỏ. Đuôi tệp do người dùng đặt, nên `virus.exe` đổi tên
thành `baocao.pdf` vẫn qua được ba bước đầu. Cách duy nhất biết một tệp thật sự
là gì là nhìn vào nội dung của nó.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.storage import minio_store
from app.models.knowledge import Notebook, Source
from app.services.ingest import SUFFIX_TO_KIND, mime_cho
from app.settings import settings

__all__ = ["UploadError", "nhan_tep"]

log = logging.getLogger(__name__)

# Chữ ký ở đầu tệp. Đây là thứ nói tệp *thật sự* là gì, khác với đuôi tệp vốn do
# người tải lên đặt tuỳ ý.
#
# `.docx` là một tệp ZIP nên bắt đầu bằng `PK`; điều đó cũng có nghĩa một tệp
# `.zip` bất kỳ đổi tên thành `.docx` sẽ qua được bước này. Bộ trích xuất phía
# sau mở nó bằng python-docx và sẽ hỏng có kiểm soát, nên đây là hàng rào thứ
# nhất chứ không phải hàng rào duy nhất.
_CHU_KY: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF",),
    "docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}

# txt và md không có chữ ký. Kiểm bằng cách khác: giải mã được UTF-8 hoặc không
# chứa byte NUL — tệp nhị phân đổi đuôi thành .txt gần như luôn có byte NUL.
_TEXT_KINDS = {"txt", "md"}

# Ảnh kiểm theo đuôi chứ không theo `kind`, vì cả bốn đuôi đều cho `kind='image'`
# nhưng có chữ ký khác hẳn nhau. Không tách ra thì một tệp PNG đổi tên thành
# `.jpg` vẫn lọt, và Pillow sẽ mở được nó — nhưng MIME ghi vào MinIO thì sai, và
# trình duyệt tải ảnh về thay vì hiển thị.
_CHU_KY_ANH: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
}


class UploadError(Exception):
    def __init__(self, message: str, code: str = "UPLOAD_REJECTED") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True, slots=True)
class KetQuaNhan:
    source_id: uuid.UUID
    storage_key: str
    kind: str
    size_bytes: int


def _kiem_duoi(ten: str) -> str:
    suffix = Path(ten).suffix.lower()
    kind = SUFFIX_TO_KIND.get(suffix)
    if kind is None:
        raise UploadError(
            f"Chưa hỗ trợ định dạng '{suffix or ten}'. "
            f"Hỗ trợ: {', '.join(sorted(SUFFIX_TO_KIND))}.",
            "KIND_UNSUPPORTED",
        )
    return kind


def _kiem_noi_dung(data: bytes, kind: str, suffix: str) -> None:
    """AC-5 — xác minh bằng nội dung, không chỉ bằng phần mở rộng."""
    if kind in _TEXT_KINDS:
        if b"\x00" in data[:8192]:
            raise UploadError(
                "Tệp khai là văn bản nhưng nội dung là dữ liệu nhị phân.",
                "CONTENT_MISMATCH",
            )
        return

    if kind == "image":
        chu_ky_anh = _CHU_KY_ANH.get(suffix, ())
        if not any(data.startswith(c) for c in chu_ky_anh):
            raise UploadError(
                f"Nội dung tệp không phải ảnh {suffix.lstrip('.').upper()} "
                f"dù phần mở rộng nói vậy.",
                "CONTENT_MISMATCH",
            )
        # RIFF là vỏ chung của nhiều định dạng (WAV, AVI). Chỉ WebP mới có
        # `WEBP` ở byte 8 — không kiểm thì một tệp âm thanh lọt qua.
        if suffix == ".webp" and data[8:12] != b"WEBP":
            raise UploadError(
                "Tệp có vỏ RIFF nhưng không phải ảnh WebP.", "CONTENT_MISMATCH"
            )
        return

    chu_ky = _CHU_KY.get(kind)
    if chu_ky and not any(data.startswith(c) for c in chu_ky):
        raise UploadError(
            f"Nội dung tệp không phải {kind.upper()} dù phần mở rộng nói vậy.",
            "CONTENT_MISMATCH",
        )


def nhan_tep(
    session: Session,
    notebook: Notebook,
    *,
    filename: str,
    data: bytes,
) -> KetQuaNhan:
    """Kiểm tra, lưu vào MinIO, tạo bản ghi `sources` ở trạng thái `queued`."""
    kind = _kiem_duoi(filename)
    suffix = Path(filename).suffix.lower()

    dang_co = session.scalar(
        select(func.count()).select_from(Source).where(Source.notebook_id == notebook.id)
    )
    if dang_co >= settings.max_sources_per_notebook:
        raise UploadError(
            f"Notebook đã đạt giới hạn {settings.max_sources_per_notebook} nguồn. "
            f"Xoá bớt trước khi thêm tài liệu mới.",
            "TOO_MANY_SOURCES",
        )

    # Ảnh có hạn mức riêng và thấp hơn nhiều. Một tấm ảnh 50 MB gần như chắc
    # chắn là ảnh máy ảnh chưa nén — nó chỉ làm OCR chậm chứ không đọc ra được
    # nhiều chữ hơn, vì `image_max_side` sẽ thu nó lại ngay sau đó.
    mb = settings.max_image_mb if kind == "image" else settings.max_file_mb
    if len(data) > mb * 1024 * 1024:
        raise UploadError(
            f"Tệp {len(data) / 1024 / 1024:.1f} MB vượt giới hạn {mb} MB.",
            "FILE_TOO_LARGE",
        )
    if not data:
        raise UploadError("Tệp rỗng.", "FILE_EMPTY")

    _kiem_noi_dung(data, kind, suffix)

    mime = mime_cho(filename)
    storage_key = minio_store.luu_tep(
        data,
        user_id=notebook.user_id,
        notebook_id=notebook.id,
        suffix=suffix,
        content_type=mime,
    )

    source = Source(
        notebook_id=notebook.id,
        title=Path(filename).stem,
        original_name=filename,
        storage_key=storage_key,
        kind=kind,
        mime_type=mime,
        size_bytes=len(data),
        status="queued",
        progress=0,
    )
    session.add(source)
    session.flush()

    log.info("Nhận %s (%s, %d byte) vào notebook %s",
             filename, kind, len(data), notebook.id)
    return KetQuaNhan(
        source_id=source.id, storage_key=storage_key, kind=kind, size_bytes=len(data)
    )
