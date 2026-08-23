"""Xuất một phiên hội thoại ra tệp — US-040.

Hai định dạng, cùng một nội dung:

* **Markdown** để dán vào bài tập, báo cáo hay ghi chú.
* **PDF** để nộp hoặc lưu, khi định dạng phải giữ nguyên.

Danh mục trích dẫn là phần bắt buộc
------------------------------------
Câu trả lời trong ứng dụng có chip bấm được; tệp xuất ra thì không. Nếu chỉ
chép nguyên văn câu trả lời thì `[1]` trở thành một ký hiệu vô nghĩa, và toàn bộ
giá trị của việc trích dẫn biến mất đúng ở nơi nó cần nhất — bản mà người khác
đọc. Vì vậy mỗi câu trả lời đi kèm danh mục "nguồn: tài liệu nào, trang bao
nhiêu" cho từng marker (AC-1).

Nhãn cảnh báo phải theo tệp ra ngoài
-------------------------------------
Câu trả lời lấy từ kiến thức ngoài tài liệu mang một nhãn cảnh báo trên giao
diện. Bỏ nhãn đó khi xuất là biến một câu trả lời "có thể sai, không kiểm chứng
được" thành một câu trả lời trông y hệt câu có căn cứ (AC-3).
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatSession
from app.models.knowledge import Notebook, Source, SourceChunk
from app.settings import settings

__all__ = ["DinhDang", "KetQuaXuat", "ten_tep", "xuat_markdown", "xuat_pdf"]

log = logging.getLogger(__name__)

DinhDang = str  # "md" | "pdf"

# Không nhúng ký hiệu "⚠" vào chính chuỗi này. Nhiều font — kể cả Arial — không
# có glyph U+26A0, và PDF sẽ in ra một khoảng trống thay vì báo lỗi. Mỗi định
# dạng tự thêm dấu hiệu cảnh báo mà nó chắc chắn hiển thị được.
NHAN_NGOAI = (
    "Câu trả lời này lấy từ kiến thức chung của mô hình, KHÔNG có trong tài "
    "liệu của bạn. Hãy tự kiểm chứng trước khi dùng."
)

_NHAN_KIND = {
    "grounded": None,
    "chitchat": None,
    "no_answer": "Không tìm thấy căn cứ trong tài liệu.",
    "external": NHAN_NGOAI,
    "cached_external": NHAN_NGOAI,
}


@dataclass(frozen=True, slots=True)
class KetQuaXuat:
    ten_tep: str
    mime: str
    noi_dung: bytes


@dataclass(frozen=True, slots=True)
class _Luot:
    cau_hoi: str
    cau_tra_loi: str
    answer_kind: str | None
    nguon: list[tuple[int, str, int | None]]
    """(marker, tên tài liệu, số trang) — đã sắp theo marker."""


def _thu_thap(session: Session, phien: ChatSession) -> list[_Luot]:
    """Ghép từng cặp hỏi–đáp kèm nguồn của nó."""
    tin_nhan = session.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == phien.id)
        .order_by(ChatMessage.seq)
    ).all()

    luot: list[_Luot] = []
    cau_hoi_dang_cho: str | None = None

    for m in tin_nhan:
        if m.role == "user":
            cau_hoi_dang_cho = m.content
            continue

        nguon: list[tuple[int, str, int | None]] = []
        for c in sorted(m.citations, key=lambda x: x.marker):
            ten = "(tài liệu đã bị xoá)"
            if c.chunk_id is not None:
                chunk = session.get(SourceChunk, c.chunk_id)
                if chunk is not None:
                    src = session.get(Source, chunk.source_id)
                    if src is not None:
                        ten = src.title
            nguon.append((c.marker, ten, c.page_no))

        luot.append(
            _Luot(
                cau_hoi=cau_hoi_dang_cho or "(không rõ câu hỏi)",
                cau_tra_loi=m.content,
                answer_kind=m.answer_kind,
                nguon=nguon,
            )
        )
        cau_hoi_dang_cho = None

    return luot


def _tieu_de(session: Session, phien: ChatSession) -> tuple[str, str]:
    nb = session.get(Notebook, phien.notebook_id)
    return (nb.title if nb else "notebook"), phien.title


def ten_tep(ten_notebook: str, dinh_dang: DinhDang, luc: datetime | None = None) -> str:
    """Tên tệp chứa tên notebook và ngày — AC-4.

    Bỏ dấu và thay ký tự đặc biệt: tên tệp tiếng Việt có dấu vẫn hợp lệ trên
    Windows và Linux, nhưng nó đi qua header HTTP `Content-Disposition` và qua
    nhiều trình duyệt khác nhau, nên đường an toàn là chỉ dùng ASCII.
    """
    luc = luc or datetime.now(UTC)
    khong_dau = "".join(
        k for k in unicodedata.normalize("NFD", ten_notebook)
        if unicodedata.category(k) != "Mn"
    ).replace("đ", "d").replace("Đ", "D")
    sach = re.sub(r"[^A-Za-z0-9]+", "-", khong_dau).strip("-").lower() or "hoi-dap"
    return f"documind-{sach[:60]}-{luc:%Y%m%d}.{dinh_dang}"


# ══════════════════════════════════════════════════════
# Markdown
# ══════════════════════════════════════════════════════


def xuat_markdown(session: Session, phien: ChatSession) -> KetQuaXuat:
    ten_nb, ten_phien = _tieu_de(session, phien)
    luot = _thu_thap(session, phien)

    dong: list[str] = [
        f"# {ten_phien}",
        "",
        f"*Notebook:* {ten_nb}  ",
        f"*Xuất lúc:* {datetime.now(UTC):%d/%m/%Y %H:%M} UTC  ",
        f"*Số lượt hỏi:* {len(luot)}",
        "",
        "---",
        "",
    ]

    for i, lt in enumerate(luot, start=1):
        dong.append(f"## {i}. {lt.cau_hoi}")
        dong.append("")

        canh_bao = _NHAN_KIND.get(lt.answer_kind or "")
        if canh_bao:
            # Blockquote để nhãn không lẫn vào nội dung câu trả lời.
            dong.append(f"> ⚠ {canh_bao}")
            dong.append("")

        dong.append(lt.cau_tra_loi)
        dong.append("")

        if lt.nguon:
            dong.append("**Nguồn trích dẫn**")
            dong.append("")
            for marker, ten, trang in lt.nguon:
                vi_tri = f", trang {trang}" if trang else ""
                dong.append(f"- `[{marker}]` {ten}{vi_tri}")
            dong.append("")

    dong.append("---")
    dong.append("")
    dong.append("*Tạo bằng DocuMind.*")

    return KetQuaXuat(
        ten_tep=ten_tep(ten_nb, "md"),
        mime="text/markdown; charset=utf-8",
        noi_dung="\n".join(dong).encode("utf-8"),
    )


# ══════════════════════════════════════════════════════
# PDF
# ══════════════════════════════════════════════════════

# Đường dẫn font Unicode, thử theo thứ tự. Ảnh Docker cài `fonts-dejavu-core`
# nên đường đầu tiên luôn có; các đường sau dành cho máy phát triển.
_FONT_UNG_VIEN = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
)


class KhongCoFont(RuntimeError):
    """Không tìm thấy font nào hiển thị được tiếng Việt."""


def tim_font(duong_dan_cau_hinh: str | None = None) -> Path:
    """Font Unicode để dựng PDF — AC-2.

    14 font chuẩn của PDF (Helvetica, Times…) **không có** ký tự tiếng Việt.
    Dùng chúng thì tệp vẫn tạo ra được, không lỗi gì, nhưng mọi chữ có dấu in ra
    thành ô vuông — một kiểu hỏng chỉ lộ ra khi mở tệp bằng mắt.
    """
    duong_dan_cau_hinh = duong_dan_cau_hinh or settings.pdf_font
    if duong_dan_cau_hinh:
        p = Path(duong_dan_cau_hinh)
        if not p.exists():
            raise KhongCoFont(
                f"PDF_FONT trỏ tới '{p}' nhưng không có tệp nào ở đó."
            )
        return p

    for ung_vien in _FONT_UNG_VIEN:
        p = Path(ung_vien)
        if p.exists():
            return p

    raise KhongCoFont(
        "Không tìm thấy font hiển thị được tiếng Việt trên máy này. "
        "Cài `fonts-dejavu-core` hoặc trỏ PDF_FONT tới một tệp .ttf."
    )


def xuat_pdf(session: Session, phien: ChatSession, font: Path | None = None) -> KetQuaXuat:
    import pymupdf

    ten_nb, ten_phien = _tieu_de(session, phien)
    luot = _thu_thap(session, phien)
    duong_font = font or tim_font()

    # A4 tính bằng điểm, lề 56pt ≈ 2cm.
    RONG, CAO, LE = 595.0, 842.0, 56.0
    RONG_CHU = RONG - 2 * LE

    doc = pymupdf.open()
    chu = pymupdf.Font(fontfile=str(duong_font))

    trang = doc.new_page(width=RONG, height=CAO)
    trang.insert_font(fontname="vi", fontfile=str(duong_font))
    y = LE

    def sang_trang() -> None:
        nonlocal trang, y
        trang = doc.new_page(width=RONG, height=CAO)
        trang.insert_font(fontname="vi", fontfile=str(duong_font))
        y = LE

    def viet(text: str, *, co: float = 10.5, mau=(0, 0, 0), lui: float = 0.0) -> None:
        """Ghi một đoạn, tự xuống dòng và tự sang trang khi hết chỗ."""
        nonlocal y
        cao_dong = co * 1.45
        for doan in text.split("\n"):
            for dong in _ngat_dong(doan, chu, co, RONG_CHU - lui):
                if y + cao_dong > CAO - LE:
                    sang_trang()
                trang.insert_text(
                    (LE + lui, y + co), dong, fontname="vi", fontsize=co, color=mau
                )
                y += cao_dong

    def cach(n: float = 8.0) -> None:
        nonlocal y
        y += n

    viet(ten_phien, co=17)
    cach(4)
    viet(
        f"Notebook: {ten_nb}\n"
        f"Xuất lúc: {datetime.now(UTC):%d/%m/%Y %H:%M} UTC · {len(luot)} lượt hỏi",
        co=9,
        mau=(0.42, 0.45, 0.5),
    )
    cach(16)

    for i, lt in enumerate(luot, start=1):
        viet(f"{i}. {lt.cau_hoi}", co=12.5, mau=(0.05, 0.15, 0.45))
        cach(5)

        canh_bao = _NHAN_KIND.get(lt.answer_kind or "")
        if canh_bao:
            # Chữ "CẢNH BÁO" thay cho biểu tượng, và màu hổ phách cùng nghĩa với
            # nhãn trên giao diện — AC-3.
            viet(f"CẢNH BÁO — {canh_bao}", co=9.5, mau=(0.72, 0.42, 0.03))
            cach(5)

        viet(lt.cau_tra_loi)
        cach(6)

        if lt.nguon:
            viet("Nguồn trích dẫn", co=9.5, mau=(0.42, 0.45, 0.5))
            for marker, ten, tr in lt.nguon:
                vi_tri = f", trang {tr}" if tr else ""
                viet(f"[{marker}] {ten}{vi_tri}", co=9.5, mau=(0.3, 0.33, 0.38), lui=12)
        cach(20)

    du_lieu = doc.tobytes()
    doc.close()

    return KetQuaXuat(
        ten_tep=ten_tep(ten_nb, "pdf"),
        mime="application/pdf",
        noi_dung=du_lieu,
    )


def _ngat_dong(doan: str, chu, co: float, rong: float) -> list[str]:
    """Ngắt một đoạn thành các dòng vừa bề rộng, đo bằng chính font sẽ dùng.

    Đo bằng font thật chứ không ước lượng theo số ký tự: tiếng Việt có dấu làm
    chữ rộng hơn, và đếm ký tự sẽ cho những dòng tràn ra ngoài lề.
    """
    if not doan.strip():
        return [""]

    dong: list[str] = []
    hien_tai = ""
    for tu in doan.split(" "):
        thu = f"{hien_tai} {tu}".strip()
        if chu.text_length(thu, fontsize=co) <= rong:
            hien_tai = thu
            continue
        if hien_tai:
            dong.append(hien_tai)
        # Một "từ" dài hơn cả dòng — URL, hoặc chuỗi không có dấu cách. Cắt
        # cứng thay vì để nó chạy ra ngoài lề.
        while chu.text_length(tu, fontsize=co) > rong:
            cat = len(tu)
            while cat > 1 and chu.text_length(tu[:cat], fontsize=co) > rong:
                cat -= 1
            dong.append(tu[:cat])
            tu = tu[cat:]
        hien_tai = tu

    if hien_tai:
        dong.append(hien_tai)
    return dong


def xuat(session: Session, phien_id: uuid.UUID, user_id: uuid.UUID,
         dinh_dang: DinhDang) -> KetQuaXuat:
    """Xuất phiên của chính người đăng nhập. Ném `LookupError` nếu không phải."""
    phien = session.scalar(
        select(ChatSession)
        .join(Notebook, Notebook.id == ChatSession.notebook_id)
        .where(ChatSession.id == phien_id, Notebook.user_id == user_id)
    )
    if phien is None:
        raise LookupError("Không tìm thấy phiên hội thoại.")

    return xuat_pdf(session, phien) if dinh_dang == "pdf" else xuat_markdown(session, phien)
