"""Soi bộ tài liệu kiểm thử — US-044 AC-1, AC-2, AC-7.

Trả lời hai câu hỏi mà không có công cụ thì phải mở từng tệp ra đoán:

1. **Bộ này thật sự gồm những gì?** Không phải theo tên tệp, mà theo thứ hệ
   thống đọc được: có lớp text hay là bản scan, chất lượng bao nhiêu, có cấu
   trúc Chương/Điều không, dài bao nhiêu trang.
2. **Còn thiếu loại nào?** `docs/CHUAN-BI-DU-LIEU.md` §4 đặt ra một danh sách
   chỉ tiêu; script này đối chiếu và nói thẳng còn thiếu gì.

Dùng **chính** đường trích xuất của sản phẩm, không dùng đường riêng. Nhờ vậy
con số ở đây là con số hệ thống thật sự thấy — nếu bộ trích xuất đọc sai một
tệp thì bảng này lộ ra ngay, thay vì để lỗi đó chui vào bộ đánh giá.

    python eval/corpus_report.py
    python eval/corpus_report.py --markdown    # dán vào NGUON.md
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters.extract import ExtractionError, extract
from app.settings import settings
from app.text.chunker import _find_headings

DOCS = ROOT / "eval" / "dataset" / "documents"
SUFFIXES = {".pdf": "pdf", ".docx": "docx", ".txt": "txt", ".md": "md"}

# Đếm ô bảng thô: dòng có nhiều cụm cách nhau bằng khoảng trắng dài hoặc tab.
_TABLE_ROW = re.compile(r"(\S+[ \t]{3,}){2,}\S+")


@dataclass
class DocInfo:
    path: Path
    kind: str
    loai: str
    """text · scan · legacy · docx — theo thứ hệ thống ĐỌC ĐƯỢC, không theo tên tệp."""

    pages: int = 0
    chars: int = 0
    quality: float = 0.0
    headings: int = 0
    has_structure: bool = False
    table_rows: int = 0
    error: str = ""

    @property
    def nhom(self) -> str:
        return self.path.parent.name


def soi(path: Path) -> DocInfo:
    kind = SUFFIXES[path.suffix.lower()]
    info = DocInfo(path=path, kind=kind, loai="?")

    try:
        r = extract(path, kind)
    except ExtractionError as e:
        info.error = e.code
        # Cổng chất lượng từ chối tệp — nhưng lý do TỪ CHỐI chính là thông tin
        # ta cần: bản scan và tệp mã cũ đều nằm ở đây.
        info.loai = {
            "SCAN_NO_TEXT_LAYER": "scan",
            "LEGACY_ENCODING_TCVN3": "legacy",
            "LEGACY_ENCODING_VNI": "legacy",
        }.get(e.code, "loi")
        return info

    info.pages = r.page_count
    info.chars = len(r.full_text)
    info.quality = r.quality.score
    info.loai = "docx" if kind == "docx" else "text"

    if kind == "pdf" and r.looks_scanned(
        chars_per_page=settings.scan_chars_per_page_threshold,
        page_ratio=settings.scan_page_ratio_threshold,
    ):
        info.loai = "scan"

    headings = _find_headings(r.full_text)
    info.headings = len(headings)
    info.has_structure = any(
        h.title.lower().startswith(("chương", "điều", "phần", "mục"))
        for h in headings
    )
    info.table_rows = len(_TABLE_ROW.findall(r.full_text))
    return info


CHI_TIEU = [
    ("Tổng số tài liệu", 10, lambda d: True),
    ("PDF có lớp text", 4, lambda d: d.kind == "pdf" and d.loai == "text"),
    ("PDF scan", 2, lambda d: d.loai == "scan"),
    ("PDF mã cũ TCVN3/VNI", 1, lambda d: d.loai == "legacy"),
    ("DOCX", 1, lambda d: d.kind == "docx"),
    ("Có bảng biểu", 1, lambda d: d.table_rows >= 10),
    ("Có cấu trúc Chương/Điều", 4, lambda d: d.has_structure),
    ("Ngắn (< 5 trang)", 2, lambda d: 0 < d.pages < 5),
    ("Dài (> 30 trang)", 1, lambda d: d.pages > 30),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Soi bộ tài liệu kiểm thử.")
    ap.add_argument("--markdown", action="store_true", help="Xuất bảng Markdown")
    args = ap.parse_args()

    files = sorted(
        p for p in DOCS.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES
    )
    if not files:
        print(f"Không có tài liệu nào trong {DOCS}", file=sys.stderr)
        return 1

    infos = [soi(p) for p in files]

    sep = "|" if args.markdown else " "
    print(f"{sep} # {sep} Tệp {sep} Nhóm {sep} Loại {sep} Trang {sep} Ký tự {sep} "
          f"Chất lượng {sep} Tiêu đề {sep} Chương/Điều {sep} Dòng bảng {sep}")
    if args.markdown:
        print("|" + "---|" * 10)

    for i, d in enumerate(infos, 1):
        note = d.error or ""
        print(
            f"{sep} {i} {sep} `{d.path.name}` {sep} {d.nhom} {sep} {d.loai}{note and ' ' + note} "
            f"{sep} {d.pages or '—'} {sep} {f'{d.chars:,}' if d.chars else '—'} {sep} "
            f"{d.quality:.2f} {sep} {d.headings} {sep} "
            f"{'có' if d.has_structure else '—'} {sep} {d.table_rows} {sep}"
        )

    print()
    print(f"{sep} Chỉ tiêu {sep} Cần {sep} Hiện có {sep} {sep}")
    if args.markdown:
        print("|" + "---|" * 4)

    thieu: list[str] = []
    for ten, can, dieu_kien in CHI_TIEU:
        co = sum(1 for d in infos if dieu_kien(d))
        dat = "✓" if co >= can else f"thiếu {can - co}"
        if co < can:
            thieu.append(f"{ten}: cần thêm {can - co}")
        print(f"{sep} {ten} {sep} {can} {sep} {co} {sep} {dat} {sep}")

    if thieu and not args.markdown:
        print("\nCòn thiếu:")
        for t in thieu:
            print(f"  - {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
