"""Hiệu chỉnh ngưỡng τ bằng dữ liệu — US-047.

Vì sao phải làm
---------------
τ = 0.35 hiện là **giá trị đoán**. Hội đồng hỏi *"vì sao 0.35?"* thì không có gì
để trả lời, và đó là loại câu hỏi rất dễ bị hỏi vì con số nằm ngay trong cấu
hình.

Cách làm
--------
Đây là bài toán phân loại nhị phân: *"câu hỏi này có đủ căn cứ trong tài liệu
không?"*. Nhãn đã có sẵn từ US-044 — câu trong phạm vi là **có**, câu ngoài
phạm vi là **không**.

Điểm cross-encoder cao nhất **không phụ thuộc τ**. Vì vậy chỉ cần chấm mỗi câu
đúng một lần, rồi quét ngưỡng bằng số học thuần. Chạy lại truy xuất cho từng
giá trị τ sẽ tốn gấp mười ba lần mà cho ra đúng cùng kết quả.

Đánh đổi phải nêu trong báo cáo (AC-4)
---------------------------------------
τ cao thì hệ thống ít bịa nhưng hay từ chối oan; τ thấp thì ngược lại. Chọn theo
F1 là chọn điểm cân bằng — nhưng cân bằng không phải lúc nào cũng đúng. Với một
hệ thống mà điểm bán là *"trả lời có trích dẫn kiểm chứng được"*, từ chối oan rẻ
hơn bịa đặt, nên đáng cân nhắc lấy τ cao hơn mức F1 tối ưu một chút. Script in
ra cả bảng để quyết định đó là quyết định có nhìn số.

    python eval/tau_sweep.py
    python eval/tau_sweep.py --lam-lai      # chấm lại điểm thay vì dùng bản lưu
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

from app.adapters.embedding import get_embedding_provider
from app.adapters.rerank import get_rerank_provider
from app.models.base import session_scope
from app.models.knowledge import Notebook, User
from app.services.grounding import decide
from app.services.retrieval import retrieve
from app.settings import settings
from chart import line_chart
from sqlalchemy import select

QUESTIONS = ROOT / "eval" / "dataset" / "questions.json"
RESULTS = ROOT / "eval" / "results"
DIEM = RESULTS / "tau-diem.json"

OWNER = "eval@documind.local"

TAU_MIN, TAU_MAX, TAU_BUOC = 0.10, 0.70, 0.05


@dataclass
class Diem:
    id: str
    top_score: float
    co_dap_an: bool
    """True nếu tài liệu THẬT SỰ chứa đáp án — nhãn từ US-044."""


def _quet() -> list[float]:
    n = round((TAU_MAX - TAU_MIN) / TAU_BUOC) + 1
    return [round(TAU_MIN + i * TAU_BUOC, 2) for i in range(n)]


def _do(diem: list[Diem], tau: float) -> dict[str, float]:
    """Precision / Recall / F1 cho bài toán "có đủ căn cứ" tại một ngưỡng."""
    tp = sum(1 for d in diem if d.co_dap_an and d.top_score >= tau)
    fp = sum(1 for d in diem if not d.co_dap_an and d.top_score >= tau)
    fn = sum(1 for d in diem if d.co_dap_an and d.top_score < tau)
    tn = sum(1 for d in diem if not d.co_dap_an and d.top_score < tau)

    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {
        "tau": tau, "precision": p, "recall": r, "f1": f1,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


async def cham_diem(lam_lai: bool) -> list[Diem]:
    """Điểm cross-encoder cao nhất cho từng câu — chấm một lần, dùng cho cả bảng."""
    if DIEM.exists() and not lam_lai:
        luu = json.loads(DIEM.read_text(encoding="utf-8"))
        print(f"Dùng điểm đã lưu ({len(luu['scores'])} câu) từ {DIEM.name}.")
        print("Chấm lại bằng --lam-lai nếu đã đổi mô hình hay cách chia đoạn.\n")
        return [Diem(**d) for d in luu["scores"]]

    data = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    trong = [c for c in data["in_scope"] if c["review"]["status"] != "rejected"]
    ngoai = [c for c in data["out_of_scope"] if c["review"]["status"] != "rejected"]
    print(f"{len(trong)} câu có đáp án + {len(ngoai)} câu không có đáp án.\n")

    emb, rr = get_embedding_provider(), get_rerank_provider()
    diem: list[Diem] = []

    with session_scope() as s:
        user = s.scalar(select(User).where(User.email == OWNER))
        user_id = user.id
        nb_id = s.scalar(select(Notebook).where(Notebook.user_id == user.id)).id

    for nhan, nhom in (("có đáp án", trong), ("không có", ngoai)):
        for i, c in enumerate(nhom, 1):
            # Phiên riêng cho từng câu: chấm 130 câu bằng CPU mất hàng giờ, và
            # một kết nối mở suốt chừng ấy là chỗ hỏng đã gặp thật.
            with session_scope() as s:
                r = retrieve(s, c["question"], notebook_id=nb_id,
                             embedder=emb, owner_id=user_id)
                d = decide(c["question"], r, reranker=rr)
            diem.append(Diem(id=c["id"], top_score=round(d.top_score, 4),
                             co_dap_an=nhan == "có đáp án"))
            print(f"  [{nhan:<9} {i}/{len(nhom)}] {c['id']}  {d.top_score:.4f}",
                  flush=True)

    RESULTS.mkdir(parents=True, exist_ok=True)
    DIEM.write_text(
        json.dumps(
            {
                "scored_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "models": {
                    "embedding": settings.embedding_model,
                    "rerank": settings.rerank_model,
                },
                "config": {
                    "retrieval_top_n_per_branch": settings.retrieval_top_n_per_branch,
                    "rrf_k": settings.rrf_k,
                    "rerank_candidates": settings.rerank_candidates,
                    "rerank_top_k": settings.rerank_top_k,
                },
                "scores": [d.__dict__ for d in diem],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    return diem


def _in_bang(bang: list[dict], tot_nhat: dict) -> None:
    print("\n" + "═" * 74)
    print(f"{'τ':>6}{'Precision':>12}{'Recall':>10}{'F1':>10}"
          f"{'TP':>6}{'FP':>6}{'FN':>6}{'TN':>6}")
    print("─" * 74)
    for h in bang:
        danh_dau = "  ← F1 cao nhất" if h["tau"] == tot_nhat["tau"] else ""
        print(f"{h['tau']:>6.2f}{h['precision']:>12.4f}{h['recall']:>10.4f}"
              f"{h['f1']:>10.4f}{h['tp']:>6}{h['fp']:>6}{h['fn']:>6}{h['tn']:>6}"
              f"{danh_dau}")
    print("─" * 74)


def _nhan_xet(bang: list[dict], tot_nhat: dict, hien_tai: float) -> None:
    ht = next((h for h in bang if abs(h["tau"] - hien_tai) < 1e-9), None)

    print(f"\nτ tối ưu theo F1: {tot_nhat['tau']:.2f}  (F1 {tot_nhat['f1']:.4f})")
    if ht:
        print(f"τ đang dùng     : {hien_tai:.2f}  (F1 {ht['f1']:.4f}, "
              f"từ chối oan {ht['fn']}, trả lời khống {ht['fp']})")

    print("\nĐánh đổi (US-047 AC-4):")
    print("  τ thấp  → ít từ chối oan, nhưng trả lời cả khi không có căn cứ.")
    print(f"            Ở τ={bang[0]['tau']:.2f}: {bang[0]['fp']} câu ngoài phạm vi "
          f"vẫn được trả lời.")
    print("  τ cao   → không bịa, nhưng từ chối cả câu trả lời được.")
    print(f"            Ở τ={bang[-1]['tau']:.2f}: {bang[-1]['fn']} câu có đáp án "
          f"bị từ chối oan.")
    print("\n  F1 chọn điểm cân bằng. Với hệ thống lấy 'trả lời có trích dẫn kiểm")
    print("  chứng được' làm điểm bán, từ chối oan rẻ hơn bịa đặt — nên cân nhắc")
    print("  lấy cao hơn mức F1 tối ưu một bậc, và nói rõ lựa chọn đó trong báo cáo.")


async def main_async(args: argparse.Namespace) -> int:
    if not QUESTIONS.exists():
        print("Chưa có bộ câu hỏi. Chạy: python eval/build_dataset.py", file=sys.stderr)
        return 1

    diem = await cham_diem(args.lam_lai)
    if not diem:
        return 1
    if not any(d.co_dap_an for d in diem) or all(d.co_dap_an for d in diem):
        print("Cần CẢ câu có đáp án lẫn câu ngoài phạm vi mới quét được ngưỡng.",
              file=sys.stderr)
        return 1

    bang = [_do(diem, t) for t in _quet()]
    tot_nhat = max(bang, key=lambda h: h["f1"])

    _in_bang(bang, tot_nhat)
    _nhan_xet(bang, tot_nhat, settings.tau)

    p = line_chart(
        RESULTS / "tau-sweep.svg",
        tieu_de=f"Hiệu chỉnh ngưỡng τ ({len(diem)} câu)",
        x=[h["tau"] for h in bang],
        day=[
            ("Precision", [h["precision"] for h in bang]),
            ("Recall", [h["recall"] for h in bang]),
            ("F1", [h["f1"] for h in bang]),
        ],
        truc_x="ngưỡng τ",
        danh_dau=tot_nhat["tau"],
        nhan_danh_dau=f"F1 cao nhất tại τ = {tot_nhat['tau']:.2f}",
    )

    out = RESULTS / "tau-sweep.json"
    out.write_text(
        json.dumps(
            {
                "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "so_cau": len(diem),
                "tau_dang_dung": settings.tau,
                "tau_toi_uu": tot_nhat["tau"],
                "bang": bang,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nBảng số : {out.relative_to(ROOT)}")
    print(f"Biểu đồ : {p.relative_to(ROOT)}")
    if abs(tot_nhat["tau"] - settings.tau) > 1e-9:
        print(f"\nCập nhật `.env`:  TAU={tot_nhat['tau']:.2f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Hiệu chỉnh ngưỡng τ (US-047).")
    ap.add_argument("--lam-lai", action="store_true",
                    help="Chấm lại điểm thay vì dùng bản đã lưu")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
