"""Spike S1 — bất biến offset trên PDF tiếng Việt thật.

Câu hỏi: sau khi trích text bằng PyMuPDF và chuẩn hoá NFC, cắt lại bằng
`full_text[char_start:char_end]` có thu được ĐÚNG nội dung chunk không?

Đây là bất biến INV-1 của SPEC-v1.md §1.3 và là rủi ro số 1 ở SPEC.md §J.6.
Nếu spike này đỏ, toàn bộ tính năng trích dẫn không dựng được như thiết kế.

Spike này cố ý mô phỏng đường đi thật ở mức tối thiểu:
    trích theo trang -> ghép thành full_text -> chuẩn hoá NFC -> chia chunk -> đối chiếu

Chạy:  python spikes/s1_offset.py
Kết quả: spikes/out/s1_offset.md
"""

from __future__ import annotations

import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    sys.exit("Thiếu PyMuPDF. Chạy: pip install -r spikes/requirements.txt")

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
OUT = ROOT / "out"

# Chunk nhỏ để tạo nhiều ranh giới -> nhiều cơ hội lộ lỗi offset.
CHUNK_CHARS = 800
OVERLAP_CHARS = 120


@dataclass
class PageSpan:
    page: int
    start: int
    end: int


@dataclass
class Chunk:
    index: int
    page: int
    char_start: int
    char_end: int
    content: str


def to_nfc(s: str) -> str:
    """Ranh giới chuẩn hoá DUY NHẤT của hệ thống (INV-2)."""
    return unicodedata.normalize("NFC", s)


def extract(pdf: Path) -> tuple[str, list[PageSpan]]:
    """Trích text theo trang rồi ghép, giữ bản đồ trang -> khoảng ký tự.

    Điểm mấu chốt: chuẩn hoá NFC **một lần trên chuỗi đã ghép**, không phải
    trên từng trang rồi mới ghép. Chuẩn hoá từng mảnh rồi ghép có thể cho
    độ dài khác với chuẩn hoá chuỗi ghép, và đó chính là cách offset lệch.
    """
    doc = fitz.open(pdf)
    raw_pages = [page.get_text("text") for page in doc]
    doc.close()

    raw_full = "".join(raw_pages)
    full = to_nfc(raw_full)

    # Nếu NFC làm đổi độ dài, bản đồ trang tính trên chuỗi thô sẽ sai.
    # Phải dựng lại bản đồ trên chuỗi ĐÃ chuẩn hoá.
    spans: list[PageSpan] = []
    cursor = 0
    for i, raw in enumerate(raw_pages, start=1):
        norm = to_nfc(raw)
        spans.append(PageSpan(page=i, start=cursor, end=cursor + len(norm)))
        cursor += len(norm)

    length_drift = cursor != len(full)
    if length_drift:
        # Cảnh báo: ghép-rồi-chuẩn-hoá khác chuẩn-hoá-rồi-ghép.
        # Ghi lại để quyết định thứ tự thao tác trong sản phẩm.
        print(
            f"  [!] Lệch độ dài: tổng trang đã chuẩn hoá = {cursor}, "
            f"chuỗi ghép đã chuẩn hoá = {len(full)}"
        )
        full = "".join(to_nfc(p) for p in raw_pages)

    return full, spans


def page_of(spans: list[PageSpan], pos: int) -> int:
    for s in spans:
        if s.start <= pos < s.end:
            return s.page
    return spans[-1].page if spans else 0


def chunk_text(full: str, spans: list[PageSpan]) -> list[Chunk]:
    chunks: list[Chunk] = []
    step = CHUNK_CHARS - OVERLAP_CHARS
    idx = 0
    pos = 0
    while pos < len(full):
        end = min(pos + CHUNK_CHARS, len(full))
        chunks.append(
            Chunk(
                index=idx,
                page=page_of(spans, pos),
                char_start=pos,
                char_end=end,
                content=full[pos:end],
            )
        )
        idx += 1
        if end == len(full):
            break
        pos += step
    return chunks


def vietnamese_signals(text: str) -> dict[str, float]:
    """Tín hiệu chất lượng thô — tiền thân của US-056."""
    if not text:
        return {"diacritic_ratio": 0.0, "replacement_ratio": 0.0, "nfc": 1.0}
    diacritics = sum(1 for c in text if "À" <= c <= "ỹ")
    replacements = text.count("�")
    return {
        "diacritic_ratio": diacritics / len(text),
        "replacement_ratio": replacements / len(text),
        "nfc": 1.0 if unicodedata.is_normalized("NFC", text) else 0.0,
    }


def check(pdf: Path) -> dict:
    print(f"\n=== {pdf.name} ===")
    full, spans = extract(pdf)
    chunks = chunk_text(full, spans)

    mismatches = [c for c in chunks if full[c.char_start : c.char_end] != c.content]
    sig = vietnamese_signals(full)

    print(f"  trang: {len(spans)}  ký tự: {len(full)}  chunk: {len(chunks)}")
    print(f"  INV-1 offset khớp: {len(chunks) - len(mismatches)}/{len(chunks)}")
    print(f"  INV-2 toàn chuỗi là NFC: {'CÓ' if sig['nfc'] else 'KHÔNG'}")
    print(f"  tỉ lệ ký tự có dấu: {sig['diacritic_ratio']:.3f}")
    print(f"  tỉ lệ ký tự thay thế (U+FFFD): {sig['replacement_ratio']:.5f}")

    if sig["diacritic_ratio"] < 0.01 and len(full) > 500:
        print("  [!] Gần như không có dấu tiếng Việt — nghi PDF scan hoặc mã cũ")

    return {
        "file": pdf.name,
        "pages": len(spans),
        "chars": len(full),
        "chunks": len(chunks),
        "mismatches": len(mismatches),
        "nfc": bool(sig["nfc"]),
        "diacritic_ratio": sig["diacritic_ratio"],
        "replacement_ratio": sig["replacement_ratio"],
        "sample": full[:300].replace("\n", " ⏎ "),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not SAMPLES.exists():
        SAMPLES.mkdir(parents=True, exist_ok=True)
        print(f"Đã tạo {SAMPLES}. Hãy đặt PDF tiếng Việt vào đó rồi chạy lại.")
        return 1

    pdfs = sorted(SAMPLES.glob("*.pdf"))
    if not pdfs:
        print(f"Không tìm thấy PDF nào trong {SAMPLES}")
        print("Cần ít nhất: một PDF có lớp text, một PDF scan.")
        return 1

    results = [check(p) for p in pdfs]

    total_chunks = sum(r["chunks"] for r in results)
    total_bad = sum(r["mismatches"] for r in results)
    all_nfc = all(r["nfc"] for r in results)
    passed = total_bad == 0 and all_nfc

    lines = [
        "# Spike S1 — bất biến offset",
        "",
        f"**Kết luận: {'ĐẠT' if passed else 'KHÔNG ĐẠT'}**",
        "",
        f"- INV-1 (offset): {total_chunks - total_bad}/{total_chunks} chunk khớp",
        f"- INV-2 (NFC): {'mọi tệp đều NFC' if all_nfc else 'CÓ TỆP KHÔNG PHẢI NFC'}",
        "",
        "| Tệp | Trang | Ký tự | Chunk | Lệch offset | NFC | Tỉ lệ dấu | U+FFFD |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['file']} | {r['pages']} | {r['chars']} | {r['chunks']} | "
            f"{r['mismatches']} | {'✓' if r['nfc'] else '✗'} | "
            f"{r['diacritic_ratio']:.3f} | {r['replacement_ratio']:.5f} |"
        )

    lines += ["", "## Mẫu 300 ký tự đầu mỗi tệp", ""]
    for r in results:
        lines += [f"**{r['file']}**", "", "```", r["sample"], "```", ""]

    lines += [
        "## Việc tiếp theo",
        "",
        "- Nếu ĐẠT: ghi quyết định vào `docs/decisions/`, giữ nguyên thiết kế "
        "`source_texts` ở SPEC-v1 §4.2.",
        "- Nếu offset lệch: xem lại thứ tự ghép/chuẩn hoá trong `extract()` — "
        "đây là chỗ hỏng phổ biến nhất.",
        "- Nếu tỉ lệ dấu < 0.01 trên tệp lẽ ra có text: đó là ca mã cũ "
        "TCVN3/VNI ở SPEC §US-007 AC-8.",
    ]

    report = OUT / "s1_offset.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nBáo cáo: {report}")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
