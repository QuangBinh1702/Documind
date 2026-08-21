"""Tải bộ tài liệu kiểm thử theo `dataset/nguon.csv` — US-044 AC-7.

Tệp gốc không nằm trong repo (`*.pdf` bị `.gitignore` loại). Đây là thứ dựng
lại đúng bộ dữ liệu đó trên một máy khác, để kết quả đánh giá ở Chương 5 tái
lập được.

**Kiểm tra sau khi tải, không chỉ tải xong là xong.** Đã gặp thật: một tệp về
19,8 MB, header `%PDF-1.7` đúng, mở ra `page_count = 0` — tải đứt giữa chừng
nhưng vẫn qua được mọi phép kiểm tra dựa trên phần đầu tệp. Tải lại đủ thì ra
43 trang. Vì vậy mỗi tệp đều được mở ra đếm trang trước khi ghi xuống đĩa.

    python eval/tai_tai_lieu.py
    python eval/tai_tai_lieu.py --lai     # tải lại cả tệp đã có
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import httpx
import pymupdf

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "dataset" / "nguon.csv"
DOCS = ROOT / "dataset" / "documents"

# Nhiều cổng thông tin của trường dùng chứng thư TLS hết hạn hoặc thiếu chuỗi
# trung gian. Đây là văn bản công khai và ta kiểm tra nội dung sau khi tải, nên
# bỏ qua xác thực chứng thư là đánh đổi chấp nhận được ở một script dựng dữ liệu.
VERIFY_TLS = False

UA = {"User-Agent": "Mozilla/5.0 (compatible; DocuMind-eval/1.0)"}


def kiem_tra(data: bytes) -> tuple[bool, str]:
    """Tệp này có dùng được không, và nó là loại gì."""
    if data[:4] != b"%PDF":
        return False, f"không phải PDF (bắt đầu bằng {data[:8]!r})"
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        return False, f"không mở được: {type(exc).__name__}"

    pages = doc.page_count
    chars = sum(len(doc[i].get_text("text").strip()) for i in range(pages))
    doc.close()

    if pages == 0:
        return False, "0 trang — tệp hỏng hoặc tải đứt giữa chừng"
    loai = "scan" if chars < 100 * pages else "text"
    return True, f"{pages} trang · {chars:,} ký tự · {loai}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Tải bộ tài liệu kiểm thử.")
    ap.add_argument("--lai", action="store_true", help="Tải lại cả tệp đã có")
    args = ap.parse_args()

    if not CSV.exists():
        print(f"Không thấy {CSV}", file=sys.stderr)
        return 1

    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    ok, bo_qua, hong = 0, 0, []

    for r in rows:
        dest = DOCS / r["nhom"] / r["ten"]
        if dest.exists() and not args.lai:
            print(f"[có sẵn] {r['ten']}")
            bo_qua += 1
            continue

        print(f"[tải]    {r['ten']}")
        try:
            resp = httpx.get(
                r["url"], timeout=120, follow_redirects=True,
                verify=VERIFY_TLS, headers=UA,
            )
        except Exception as exc:
            print(f"         THẤT BẠI: {type(exc).__name__}")
            hong.append((r["ten"], type(exc).__name__))
            continue

        if resp.status_code != 200:
            print(f"         THẤT BẠI: HTTP {resp.status_code}")
            hong.append((r["ten"], f"HTTP {resp.status_code}"))
            continue

        dung_duoc, mo_ta = kiem_tra(resp.content)
        if not dung_duoc:
            print(f"         THẤT BẠI: {mo_ta}")
            hong.append((r["ten"], mo_ta))
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        print(f"         {mo_ta} · {len(resp.content) / 1024:.0f} KB")
        ok += 1

    print()
    print(f"Tải được {ok}, bỏ qua {bo_qua}, thất bại {len(hong)} / {len(rows)} mục.")
    if hong:
        print("\nThất bại:")
        for ten, ly_do in hong:
            print(f"  {ten:<46} {ly_do}")
        print(
            "\nLink văn bản của các trường hay chết. Tìm bản khác rồi cập nhật "
            "URL trong dataset/nguon.csv."
        )

    print("\nĐối chiếu chỉ tiêu:  python eval/corpus_report.py")
    return 0 if not hong else 1


if __name__ == "__main__":
    raise SystemExit(main())
