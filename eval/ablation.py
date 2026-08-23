"""Nghiên cứu loại trừ — US-046.

Câu hỏi cần trả lời: **từng thành phần đóng góp bao nhiêu?** Không có bảng này
thì mọi lựa chọn kỹ thuật trong đồ án chỉ là làm theo hướng dẫn — hội đồng hỏi
*"vì sao dùng hybrid mà không dùng vector thuần?"* thì không có gì để đưa ra.

Sáu cấu hình, hai chiều cải tiến khác nhau::

    A  chỉ vector              ─┐
    B  chỉ từ khoá              │  chất lượng TRUY XUẤT
    C  hybrid (RRF)             │
    D  hybrid + rerank         ─┘
    E  D + Contextual Retrieval ─┐  chất lượng NGỮ CẢNH
    F  D + tác tử kiểm định     ─┘  và SINH PHẢN HỒI

Đó là điều làm bảng này mạnh hơn một dãy tăng dần đơn thuần: E và F không nằm
trên cùng một trục với A→D, nên chúng trả lời hai câu hỏi khác nhau.

Cùng bộ test, cùng hạt giống, cùng mô hình
-------------------------------------------
US-046 AC-6. Chỉ đúng cờ đang khảo sát được đổi. Cắt bớt số câu thì cắt từ ĐẦU
danh sách, không lấy ngẫu nhiên — hai cấu hình chạy trên hai tập con khác nhau
thì con số không so được với nhau, mà bảng lại trông vẫn bình thường.

Dòng E không chỉ là một cờ
---------------------------
Năm cấu hình còn lại đổi hành vi **lúc truy vấn**, nên bật/tắt là đủ. Riêng
Contextual Retrieval đổi hành vi **lúc nạp tài liệu**: prefix bối cảnh được sinh
rồi đưa vào vector và `tsv` từ lúc lập chỉ mục. Bật cờ đó ở đây trên một chỉ mục
chưa có prefix thì dòng E ra giống hệt dòng D — và không có gì trong bảng để lộ
điều đó. Script kiểm tra chỉ mục trước và từ chối chạy nếu chưa nạp kèm bối cảnh.

Chi phí thật
------------
Cross-encoder chạy trên CPU mất khoảng 35 giây mỗi câu hỏi. Ba cấu hình D, E, F
đều có rerank, nên một lượt đầy đủ 100 câu là khoảng ba giờ chỉ riêng phần đó.
Bảng đầy đủ cho báo cáo phải chạy trên máy đích. Trên laptop hãy dùng `--so-cau`
để lấy một lát cắt và kiểm chứng đường ống trước.

    python eval/ablation.py --so-cau 20        # lát cắt, chạy được trên laptop
    python eval/ablation.py                    # đầy đủ, nên chạy trên máy đích
    python eval/ablation.py --chi A B C D      # chạy lại vài cấu hình
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

from app.settings import settings
from chart import bar_chart
from run_eval import NGUONG, OWNER, RESULTS, KetQua, _trung_binh, chay

# Mỗi cấu hình là tập cờ khác mặc định. Cờ nào không nêu thì giữ nguyên giá trị
# trong `.env` — nhờ vậy bảng này khảo sát đúng thứ nó nói là đang khảo sát.
CAU_HINH: dict[str, tuple[str, dict]] = {
    "A": ("Chỉ vector", {
        "retrieval_vector_enabled": True, "retrieval_bm25_enabled": False,
        "rerank_enabled": False, "contextual_retrieval_enabled": False,
        "verifier_enabled": False,
    }),
    "B": ("Chỉ từ khoá", {
        "retrieval_vector_enabled": False, "retrieval_bm25_enabled": True,
        "rerank_enabled": False, "contextual_retrieval_enabled": False,
        "verifier_enabled": False,
    }),
    "C": ("Hybrid + RRF", {
        "retrieval_vector_enabled": True, "retrieval_bm25_enabled": True,
        "rerank_enabled": False, "contextual_retrieval_enabled": False,
        "verifier_enabled": False,
    }),
    "D": ("Hybrid + rerank", {
        "retrieval_vector_enabled": True, "retrieval_bm25_enabled": True,
        "rerank_enabled": True, "contextual_retrieval_enabled": False,
        "verifier_enabled": False,
    }),
    "E": ("D + Contextual Retrieval", {
        "retrieval_vector_enabled": True, "retrieval_bm25_enabled": True,
        "rerank_enabled": True, "contextual_retrieval_enabled": True,
        "verifier_enabled": False,
    }),
    "F": ("D + tác tử kiểm định", {
        "retrieval_vector_enabled": True, "retrieval_bm25_enabled": True,
        "rerank_enabled": True, "contextual_retrieval_enabled": False,
        "verifier_enabled": True,
    }),
}

CHI_SO = ["context_recall", "context_precision", "faithfulness", "answer_relevancy"]


def _ap_dung(cau_hinh: dict) -> dict:
    """Đặt cờ, trả về giá trị cũ để khôi phục."""
    cu = {k: getattr(settings, k) for k in cau_hinh}
    for k, v in cau_hinh.items():
        setattr(settings, k, v)
    return cu


def _co_boi_canh_trong_chi_muc() -> bool:
    """Chỉ mục có prefix bối cảnh chưa — điều kiện để dòng E có nghĩa.

    Năm cờ còn lại đều tác động **lúc truy vấn**, nên bật/tắt là đủ. Riêng
    `CONTEXTUAL_RETRIEVAL_ENABLED` tác động lúc **nạp tài liệu**: nó quyết định
    có sinh prefix rồi đưa vào vector và `tsv` hay không.

    Bật cờ đó ở đây mà chỉ mục chưa có prefix thì dòng E ra **giống hệt dòng
    D** — và bảng vẫn trông hoàn toàn bình thường. Đó là kiểu sai nguy hiểm
    nhất trong một nghiên cứu loại trừ: kết luận "Contextual Retrieval không
    đóng góp gì" trong khi thật ra nó chưa từng được bật.
    """
    from app.models.base import session_scope
    from app.models.knowledge import Notebook, SourceChunk, User
    from sqlalchemy import func, select

    with session_scope() as s:
        return bool(
            s.scalar(
                select(func.count())
                .select_from(SourceChunk)
                .join(Notebook, Notebook.id == SourceChunk.notebook_id)
                .join(User, User.id == Notebook.user_id)
                .where(User.email == OWNER, SourceChunk.context_prefix.isnot(None))
            )
        )


async def main_async(args: argparse.Namespace) -> int:
    ma = args.chi or list(CAU_HINH)
    khong_biet = [m for m in ma if m not in CAU_HINH]
    if khong_biet:
        print(f"Cấu hình không có: {khong_biet}. Có: {list(CAU_HINH)}", file=sys.stderr)
        return 1

    if "E" in ma and not _co_boi_canh_trong_chi_muc():
        print(
            "Dòng E cần chỉ mục ĐÃ nạp kèm bối cảnh, mà chỉ mục hiện tại thì không.\n"
            "Bật cờ ở đây cũng không tạo ra prefix — nó được sinh lúc nạp tài liệu.\n"
            "Chạy E bây giờ sẽ ra kết quả giống hệt dòng D và bảng vẫn trông bình\n"
            "thường, tức là một kết luận sai mà không có gì để lộ.\n\n"
            "Nạp lại kèm bối cảnh rồi chạy lại:\n"
            "    CONTEXTUAL_RETRIEVAL_ENABLED=true python eval/build_dataset.py --nap\n\n"
            "Hoặc bỏ dòng E:  python eval/ablation.py --chi A B C D F",
            file=sys.stderr,
        )
        return 1

    if args.so_cau:
        print(f"[!] Chỉ chạy {args.so_cau} câu đầu — đây là LÁT CẮT để kiểm chứng "
              f"đường ống, không phải số liệu cho báo cáo.\n")

    bang: dict[str, list[KetQua]] = {}
    for m in ma:
        ten, cau_hinh = CAU_HINH[m]
        print(f"\n{'═' * 70}\nCấu hình {m} — {ten}\n{'═' * 70}")
        cu = _ap_dung(cau_hinh)
        try:
            kq = await chay(
                nhan=f"ablation-{m}",
                chi_truy_xuat=args.chi_truy_xuat,
                bo_cham=args.bo_cham,
                lam_lai=args.lam_lai,
                so_cau=args.so_cau,
            )
        finally:
            _ap_dung(cu)

        if not kq:
            print(f"Cấu hình {m} không có kết quả.", file=sys.stderr)
            return 1
        bang[m] = kq

    _bang(bang, args)
    _ve(bang, args)
    return 0


def _bang(bang: dict[str, list[KetQua]], args) -> None:
    print("\n" + "═" * 96)
    print("BẢNG ABLATION — US-046 AC-2")
    print("═" * 96)

    tieu = f"{'':>3} {'Cấu hình':<26}"
    for c in CHI_SO:
        tieu += f"{c.replace('_', ' ')[:14]:>15}"

    print(tieu + f"{'pass':>8}{'trễ p50':>10}")
    print("─" * 96)

    dong: list[str] = []
    for m, kq in bang.items():
        ten = CAU_HINH[m][0]
        d = f"{m:>3} {ten:<26}"
        for c in CHI_SO:
            tb, _ = _trung_binh(kq, c)
            d += f"{'—':>15}" if tb is None else f"{tb:>15.4f}"
        dat = sum(1 for k in kq if k.dat) / len(kq)
        tre = sorted(k.latency_ms for k in kq)
        d += f"{dat:>7.1%}{tre[len(tre) // 2]:>9}ms"
        print(d)
        dong.append(d)

    print("─" * 96)
    print("Ngưỡng tối thiểu: " + " · ".join(f"{c}={NGUONG[c]}" for c in CHI_SO))

    tom_tat = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "so_cau": len(next(iter(bang.values()))),
        "la_lat_cat": bool(args.so_cau),
        "chi_truy_xuat": args.chi_truy_xuat,
        "cau_hinh": {
            m: {
                "ten": CAU_HINH[m][0],
                "co": CAU_HINH[m][1],
                "chi_so": {
                    c: (lambda t: None if t[0] is None else round(t[0], 4))(
                        _trung_binh(kq, c)
                    )
                    for c in CHI_SO
                },
                "pass_rate": round(sum(1 for k in kq if k.dat) / len(kq), 4),
                "latency_p50_ms": sorted(k.latency_ms for k in kq)[len(kq) // 2],
            }
            for m, kq in bang.items()
        },
    }
    p = RESULTS / "ablation.json"
    p.write_text(json.dumps(tom_tat, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTóm tắt: {p.relative_to(ROOT)}")


def _ve(bang: dict[str, list[KetQua]], args) -> None:
    ma = list(bang)
    nhan = [f"{m}\n{CAU_HINH[m][0][:16]}" for m in ma]

    day = []
    for c in CHI_SO:
        gia_tri = []
        co_du_lieu = False
        for m in ma:
            tb, _ = _trung_binh(bang[m], c)
            gia_tri.append(round(tb, 4) if tb is not None else 0.0)
            co_du_lieu = co_du_lieu or tb is not None
        if co_du_lieu:
            day.append((c.replace("_", " "), gia_tri))

    hau_to = f" ({len(next(iter(bang.values())))} câu)"
    p = bar_chart(
        RESULTS / "ablation.svg",
        tieu_de="Ablation — đóng góp của từng thành phần" + hau_to,
        nhom=nhan, day=day, truc_y="điểm trung bình", y_max=1.0,
    )
    print(f"Biểu đồ: {p.relative_to(ROOT)}")

    tre = [(m, sorted(k.latency_ms for k in bang[m])[len(bang[m]) // 2]) for m in ma]
    p2 = bar_chart(
        RESULTS / "ablation-do-tre.svg",
        tieu_de="Ablation — độ trễ trung vị" + hau_to,
        nhom=nhan, day=[("mili giây", [float(t) for _, t in tre])],
        truc_y="ms",
    )
    print(f"Biểu đồ: {p2.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Nghiên cứu loại trừ (US-046).")
    ap.add_argument("--chi", nargs="*", help="Chỉ chạy các cấu hình này, ví dụ: A B C")
    ap.add_argument("--so-cau", type=int, default=None,
                    help="Lát cắt N câu đầu — để kiểm chứng đường ống trên laptop")
    ap.add_argument("--chi-truy-xuat", action="store_true",
                    help="Bỏ phần chấm bằng mô hình; nhanh hơn nhiều, chỉ đo truy xuất")
    ap.add_argument("--bo-cham", default=None, help="Mô hình chấm (US-045 AC-9)")
    ap.add_argument("--lam-lai", action="store_true", help="Bỏ kết quả cũ")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
