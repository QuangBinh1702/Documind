"""Hiệu chỉnh ngưỡng bộ nhớ đệm bằng dữ liệu — US-064.

Vì sao phải làm
---------------
`EXTERNAL_CACHE_SIMILARITY = 0.93` hiện là **giá trị đoán**, và nó là loại con
số rất dễ bị hỏi *"vì sao 0.93?"* vì nó nằm ngay trong cấu hình.

Con số này quyết định điều gì
------------------------------
Khi người dùng hỏi ra ngoài tài liệu, hệ thống nhúng câu hỏi rồi tìm trong
những câu họ đã hỏi trước đó. Vượt ngưỡng thì trả lại câu trả lời cũ, không gọi
API. Hai chiều hỏng khác hẳn nhau về mức độ:

* **Ngưỡng quá cao** — bỏ lỡ cơ hội dùng lại. Tốn thêm một lượt gọi API. Phiền,
  nhưng không sai.
* **Ngưỡng quá thấp** — trả lời câu hỏi này bằng câu trả lời của câu hỏi khác.
  Người dùng nhận về nội dung của **Điều 15** khi họ hỏi về **Điều 5**, và không
  có dấu hiệu gì để nhận ra. Đây là loại lỗi mà cả đồ án được xây để tránh.

Vì vậy bảng kết quả in ra cả Precision lẫn Recall, và mục "khuyến nghị" nghiêng
về Precision chứ không lấy thẳng F1 tối ưu.

Vì sao bộ mẫu trông như vậy
----------------------------
Với `bge-m3`, phân bố cosine bị nén rất cao: hai câu tiếng Việt chẳng liên quan
gì vẫn thường vượt 0.6. Một bộ mẫu chỉ gồm "cặp giống nhau" và "cặp ngẫu nhiên"
sẽ cho ra F1 gần 1.0 ở mọi ngưỡng — đẹp và vô dụng.

Nên bộ mẫu có ba nhóm, và nhóm giữa mới là nhóm quyết định:

1. cặp cùng ý, khác cách diễn đạt
2. **cặp cùng khuôn câu nhưng khác một chi tiết mang nghĩa** — "Điều 5" với
   "Điều 15", "năm 2023" với "năm 2024"
3. cặp không liên quan gì nhau

    python eval/hieu_chinh_cache.py
    python eval/hieu_chinh_cache.py --lam-lai
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

from app.adapters.embedding import get_embedding_provider
from app.settings import settings
from chart import line_chart

CAP = ROOT / "eval" / "dataset" / "cap_cache.json"
RESULTS = ROOT / "eval" / "results"
DIEM = RESULTS / "cache-diem.json"

# Khoảng quét theo AC-1.
MIN, MAX, BUOC = 0.85, 0.97, 0.01


@dataclass(frozen=True, slots=True)
class Cap:
    a: str
    b: str
    trung_y: bool
    ghi_chu: str
    cosine: float


def _cosine(u: list[float], v: list[float]) -> float:
    """Hai vector của bge-m3 đã chuẩn hoá, nên tích vô hướng chính là cosine.

    Vẫn chia cho chuẩn để không phụ thuộc vào tính chất ấy: đổi mô hình nhúng là
    đổi giả định, và một phép chia rẻ hơn một con số sai âm thầm.
    """
    tich = sum(x * y for x, y in zip(u, v, strict=True))
    chuan_u = sum(x * x for x in u) ** 0.5
    chuan_v = sum(y * y for y in v) ** 0.5
    return tich / (chuan_u * chuan_v) if chuan_u and chuan_v else 0.0


def cham_diem() -> list[Cap]:
    """Nhúng mọi câu rồi tính cosine từng cặp."""
    du_lieu = json.loads(CAP.read_text(encoding="utf-8"))
    cap_tho = du_lieu["cap"]

    # Nhúng theo lô, và nhúng mỗi câu ĐÚNG MỘT LẦN dù nó xuất hiện ở nhiều cặp.
    cau: list[str] = []
    for c in cap_tho:
        cau.extend([c["a"], c["b"]])
    duy_nhat = list(dict.fromkeys(cau))

    embedder = get_embedding_provider()
    print(f"Nhúng {len(duy_nhat)} câu bằng {embedder.name} …")
    vectors = embedder.embed_documents(duy_nhat)
    bang = dict(zip(duy_nhat, vectors, strict=True))

    return [
        Cap(
            a=c["a"], b=c["b"], trung_y=bool(c["trung_y"]),
            ghi_chu=c.get("ghi_chu", ""),
            cosine=_cosine(bang[c["a"]], bang[c["b"]]),
        )
        for c in cap_tho
    ]


def do_luong(cap: list[Cap], nguong: float) -> tuple[float, float, float]:
    """Precision, Recall, F1 khi coi "cosine ≥ nguong" là dự đoán "trùng ý"."""
    tp = sum(1 for c in cap if c.cosine >= nguong and c.trung_y)
    fp = sum(1 for c in cap if c.cosine >= nguong and not c.trung_y)
    fn = sum(1 for c in cap if c.cosine < nguong and c.trung_y)

    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lam-lai", action="store_true",
                        help="nhúng lại thay vì dùng điểm đã lưu")
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)

    if DIEM.exists() and not args.lam_lai:
        luu = json.loads(DIEM.read_text(encoding="utf-8"))
        cap = [Cap(**c) for c in luu["cap"]]
        print(f"Dùng điểm đã lưu ({luu['luc']}). Thêm --lam-lai để chấm lại.\n")
    else:
        cap = cham_diem()
        DIEM.write_text(
            json.dumps(
                {
                    "luc": datetime.now(UTC).isoformat(timespec="seconds"),
                    "mo_hinh": settings.embedding_model,
                    # `asdict` chứ không `__dict__`: dataclass khai `slots=True`
                    # thì không có `__dict__` nào để đọc.
                    "cap": [asdict(c) for c in cap],
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Đã lưu điểm vào {DIEM.relative_to(ROOT)}\n")

    trung = [c for c in cap if c.trung_y]
    khac = [c for c in cap if not c.trung_y]
    print(f"{len(trung)} cặp trùng ý · {len(khac)} cặp khác ý\n")

    # ── Phân bố ────────────────────────────────────────
    print("Phân bố cosine")
    print(f"  trùng ý : thấp nhất {min(c.cosine for c in trung):.4f} · "
          f"cao nhất {max(c.cosine for c in trung):.4f}")
    print(f"  khác ý  : thấp nhất {min(c.cosine for c in khac):.4f} · "
          f"cao nhất {max(c.cosine for c in khac):.4f}")

    chong_lan = max(c.cosine for c in khac) - min(c.cosine for c in trung)
    if chong_lan > 0:
        print(f"  → hai phân bố CHỒNG LẤN {chong_lan:.4f}. Không có ngưỡng nào "
              f"tách được hoàn toàn.\n")
    else:
        print("  → hai phân bố tách rời. Mọi ngưỡng ở giữa đều đúng hết.\n")

    # ── Quét ngưỡng ────────────────────────────────────
    xs: list[float] = []
    ps: list[float] = []
    rs: list[float] = []
    fs: list[float] = []

    print(f"{'ngưỡng':>8} {'P':>8} {'R':>8} {'F1':>8}   {'nhầm':>5}")
    print("-" * 46)
    n = round((MAX - MIN) / BUOC) + 1
    for i in range(n):
        t = round(MIN + i * BUOC, 4)
        p, r, f1 = do_luong(cap, t)
        nham = sum(1 for c in cap if c.cosine >= t and not c.trung_y)
        xs.append(t)
        ps.append(p)
        rs.append(r)
        fs.append(f1)
        print(f"{t:8.2f} {p:8.4f} {r:8.4f} {f1:8.4f}   {nham:5d}")

    tot_f1 = max(range(len(xs)), key=lambda i: fs[i])
    # Ngưỡng thấp nhất mà không còn cặp khác ý nào lọt qua.
    sach = [i for i in range(len(xs)) if ps[i] >= 1.0]
    tot_p = min(sach) if sach else None

    print()
    print(f"F1 cao nhất       : τ_cache = {xs[tot_f1]:.2f}  "
          f"(P={ps[tot_f1]:.3f} R={rs[tot_f1]:.3f} F1={fs[tot_f1]:.3f})")
    if tot_p is not None:
        print(f"Không nhầm lẫn nào: τ_cache = {xs[tot_p]:.2f}  "
              f"(P={ps[tot_p]:.3f} R={rs[tot_p]:.3f} F1={fs[tot_p]:.3f})")
    else:
        print("Không ngưỡng nào trong khoảng quét loại hết được cặp khác ý.")

    print(f"\nGiá trị đang dùng : {settings.external_cache_similarity:.2f}")

    print("\nKHUYẾN NGHỊ")
    print("  Lấy ngưỡng 'không nhầm lẫn nào' nếu nó không quá xa mức F1 tối ưu.")
    print("  Hai chiều hỏng không cân nhau: bỏ lỡ một lượt dùng lại chỉ tốn thêm")
    print("  một lần gọi API, còn trả nhầm câu trả lời của một điều khoản khác thì")
    print("  người dùng không có cách nào nhận ra.")

    # ── Những cặp khó nhất ─────────────────────────────
    print("\nNhững cặp KHÁC ý có cosine cao nhất — đây là thứ ngưỡng phải chặn:")
    for c in sorted(khac, key=lambda c: -c.cosine)[:5]:
        print(f"  {c.cosine:.4f}  {c.a}")
        print(f"          {c.b}")
        if c.ghi_chu:
            print(f"          ({c.ghi_chu})")

    print("\nNhững cặp TRÙNG ý có cosine thấp nhất — đây là thứ ngưỡng dễ bỏ lỡ:")
    for c in sorted(trung, key=lambda c: c.cosine)[:5]:
        print(f"  {c.cosine:.4f}  {c.a}")
        print(f"          {c.b}")
        if c.ghi_chu:
            print(f"          ({c.ghi_chu})")

    # ── Đồ thị ─────────────────────────────────────────
    hinh = RESULTS / "hieu-chinh-cache.svg"
    line_chart(
        hinh,
        tieu_de="Hiệu chỉnh ngưỡng bộ nhớ đệm (US-064)",
        x=xs,
        day=[("Precision", ps), ("Recall", rs), ("F1", fs)],
        truc_x="ngưỡng cosine",
        danh_dau=xs[tot_f1],
        nhan_danh_dau=f"F1 cao nhất: {xs[tot_f1]:.2f}",
    )
    print(f"\nĐồ thị: {hinh.relative_to(ROOT)}")
    print("Đặt cạnh 'tau-sweep.svg' của US-047 khi đưa vào báo cáo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
