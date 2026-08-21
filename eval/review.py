"""Rà soát bộ câu hỏi do mô hình sinh — US-044 AC-6.

Vì sao bước này không bỏ được
------------------------------
Câu hỏi ở `questions.json` do mô hình sinh ra. Chúng trông rất thuyết phục và
phần lớn là đúng, nhưng ba dạng hỏng dưới đây xuất hiện đều đặn và không có cách
nào phát hiện tự động:

* **Đáp án sai một chi tiết.** Mô hình đọc "ba mươi ngày" thành "ba tháng".
  Câu hỏi vẫn hợp lý, ground truth vẫn trỏ đúng đoạn, chỉ có đáp án là sai — và
  mọi chỉ số chấm dựa trên đáp án đó đều sai theo.
* **Câu hỏi không tự đứng được.** "Thời hạn nêu ở khoản này là bao lâu?" — hỏi
  ngoài ngữ cảnh thì vô nghĩa, nhưng bộ sinh không thấy vấn đề vì nó đang nhìn
  thấy đoạn văn.
* **Đáp án có ở nhiều nơi.** Sáu quy chế trường trong bộ nói những điều rất
  giống nhau. Một câu hỏi chung chung có thể được trả lời đúng từ một tài liệu
  khác, và khi đó ground truth một-đoạn là quá hẹp — hệ thống trả lời đúng vẫn
  bị chấm là trượt.

`SPEC.md` US-044 AC-6 yêu cầu ghi lại **tỉ lệ bị loại và bị sửa** rồi đưa vào
báo cáo như một phần của phương pháp, không giấu. Con số đó nói lên độ tin cậy
của cả bộ test, nên nó đáng giá hơn một bộ test trông sạch sẽ mà không ai biết
đã qua tay ai.

    python eval/review.py              # rà từng câu chưa duyệt
    python eval/review.py --thong-ke   # chỉ xem đã rà tới đâu
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "eval" / "dataset" / "questions.json"

HUONG_DAN = """
  [Enter] giữ nguyên — câu hỏi và đáp án đều đúng
  s       sửa — nhập lại câu hỏi và/hoặc đáp án
  l       loại — câu này không dùng được
  ?       xem lại đoạn văn gốc đầy đủ
  q       dừng, lưu lại phần đã rà
"""


def _doc() -> dict:
    if not FILE.exists():
        print(f"Chưa có {FILE.relative_to(ROOT)}. Chạy: python eval/build_dataset.py",
              file=sys.stderr)
        raise SystemExit(1)
    return json.loads(FILE.read_text(encoding="utf-8"))


def _ghi(data: dict) -> None:
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def thong_ke(data: dict) -> None:
    for nhom in ("in_scope", "out_of_scope"):
        muc = data.get(nhom, [])
        if not muc:
            continue
        dem = Counter(m["review"]["status"] for m in muc)
        da_ra = sum(v for k, v in dem.items() if k != "pending")
        sua = sum(1 for m in muc if m["review"].get("edited"))

        print(f"\n{nhom} — {len(muc)} câu")
        print(f"  đã rà     {da_ra}/{len(muc)}")
        for trang_thai, n in sorted(dem.items()):
            print(f"    {trang_thai:<10} {n}")
        if da_ra:
            print(f"  tỉ lệ loại  {dem.get('rejected', 0) / da_ra:.1%}")
            print(f"  tỉ lệ sửa   {sua / da_ra:.1%}")

    print("\nHai tỉ lệ trên vào phần phương pháp của Chương 5 (US-044 AC-6).")


def _hien(m: dict, i: int, tong: int, trong_pham_vi: bool) -> None:
    print("\n" + "═" * 74)
    print(f"[{i}/{tong}]  {m['id']}  ·  {m.get('type', '')}")
    if trong_pham_vi:
        print(f"nguồn: {m['source']} · trang {m['page']} · "
              f"ký tự {m['char_start']}–{m['char_end']}")
    print("─" * 74)
    print(f"HỎI : {m['question']}")
    if trong_pham_vi:
        print(f"ĐÁP : {m['answer']}")
        print("─" * 74)
        doan = m["context"]
        print("ĐOẠN:", doan[:600] + (" …" if len(doan) > 600 else ""))
    else:
        print(f"điểm truy xuất cao nhất: {m.get('top_score', 0):.3f}")


def ra_soat(data: dict) -> None:
    for nhom in ("in_scope", "out_of_scope"):
        muc = data.get(nhom, [])
        chua = [m for m in muc if m["review"]["status"] == "pending"]
        if not chua:
            continue

        print(f"\n╔══ {nhom}: còn {len(chua)}/{len(muc)} câu chưa rà ══╗")
        print(HUONG_DAN)

        for i, m in enumerate(chua, 1):
            _hien(m, i, len(chua), nhom == "in_scope")

            while True:
                lenh = input("\n> ").strip().lower()

                if lenh == "?" and nhom == "in_scope":
                    print("\n" + m["context"])
                    continue

                if lenh == "q":
                    _ghi(data)
                    print(f"\nĐã lưu. Còn {len(chua) - i + 1} câu chưa rà.")
                    return

                if lenh == "l":
                    m["review"] = {"status": "rejected", "edited": False,
                                   "at": datetime.now(UTC).isoformat(timespec="seconds")}
                    print("  → loại")
                    break

                if lenh == "s":
                    q = input("  câu hỏi mới (Enter giữ nguyên):\n  ").strip()
                    if q:
                        m["question"] = q
                    if nhom == "in_scope":
                        a = input("  đáp án mới (Enter giữ nguyên):\n  ").strip()
                        if a:
                            m["answer"] = a
                    m["review"] = {"status": "accepted", "edited": True,
                                   "at": datetime.now(UTC).isoformat(timespec="seconds")}
                    print("  → đã sửa và giữ")
                    break

                if lenh == "":
                    m["review"] = {"status": "accepted", "edited": False,
                                   "at": datetime.now(UTC).isoformat(timespec="seconds")}
                    print("  → giữ nguyên")
                    break

                print("  lệnh không hợp lệ." + HUONG_DAN)

            # Lưu sau MỖI câu. Rà 130 câu là việc dài; mất điện hay lỡ tay đóng
            # cửa sổ không được phép xoá sạch công sức.
            _ghi(data)

    _ghi(data)
    print("\nĐã rà xong toàn bộ.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Rà soát bộ câu hỏi (US-044 AC-6).")
    ap.add_argument("--thong-ke", action="store_true", help="Chỉ xem tiến độ")
    args = ap.parse_args()

    data = _doc()
    if args.thong_ke:
        thong_ke(data)
        return 0

    ra_soat(data)
    thong_ke(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
