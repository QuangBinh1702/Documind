"""Spike S2 — ngân sách VRAM trên máy đích.

Câu hỏi: bge-m3 + bge-reranker-v2-m3 + LLM cục bộ + PaddleOCR có cùng nằm
trong 16 GB không, và với runtime nào?

Quyết định phụ thuộc: Ollama (cấp phát động) hay vLLM (tiền cấp phát theo
`gpu_memory_utilization`). Xem SPEC-v1.md §10. Chi phối cả M3 và M4.

PHẢI chạy trên server 16 GB. Trên laptop 2 GB nó sẽ dừng sớm và báo rõ.

Chạy:  python spikes/s2_vram.py
Kết quả: spikes/out/s2_vram.md
"""

from __future__ import annotations

import gc
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"

MIN_VRAM_GB = 14.0  # dưới mức này thì không phải máy đích


def nvidia_smi() -> tuple[str, float] | None:
    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        ).strip()
    except Exception:
        return None
    name, total = (x.strip() for x in raw.splitlines()[0].split(","))
    return name, float(total) / 1024.0


def vram_used_gb() -> float:
    import torch

    return torch.cuda.memory_allocated() / 1024**3


def vram_reserved_gb() -> float:
    import torch

    return torch.cuda.memory_reserved() / 1024**3


def free_all() -> None:
    import torch

    gc.collect()
    torch.cuda.empty_cache()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str, str]] = []
    notes: list[str] = []

    gpu = nvidia_smi()
    if gpu is None:
        print("Không tìm thấy nvidia-smi. Spike này cần máy có GPU NVIDIA.")
        return 1
    name, total_gb = gpu
    print(f"GPU: {name} — {total_gb:.1f} GB\n")

    if total_gb < MIN_VRAM_GB:
        print(f"[!] GPU chỉ có {total_gb:.1f} GB — đây KHÔNG phải máy đích.")
        print("    Spike S2 phải chạy trên server 16 GB thì kết quả mới có nghĩa.")
        print("    Dừng lại để tránh ghi ra số liệu gây hiểu nhầm.")
        return 1

    try:
        import torch
    except ImportError:
        print("Thiếu torch. Cài bản CUDA đúng với driver trước khi chạy.")
        return 1

    if not torch.cuda.is_available():
        print("torch không thấy CUDA. Kiểm tra bản cài đặt torch.")
        return 1

    baseline = vram_reserved_gb()
    rows.append(("(khởi điểm)", f"{baseline:.2f}", "—"))

    # ── 1. Embedding ────────────────────────────────────────
    print("Nạp bge-m3 ...")
    try:
        from FlagEmbedding import BGEM3FlagModel

        before = vram_reserved_gb()
        emb = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
        emb.encode(["câu thử tiếng Việt có dấu"], batch_size=1)
        after = vram_reserved_gb()
        rows.append(("bge-m3 (fp16)", f"{after - before:.2f}", f"tổng {after:.2f}"))
        print(f"  +{after - before:.2f} GB (tổng {after:.2f} GB)")
    except Exception as e:
        rows.append(("bge-m3 (fp16)", "LỖI", str(e)[:80]))
        notes.append(f"bge-m3 không nạp được: {e}")
        emb = None

    # ── 2. Reranker ─────────────────────────────────────────
    print("Nạp bge-reranker-v2-m3 ...")
    try:
        from FlagEmbedding import FlagReranker

        before = vram_reserved_gb()
        rr = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True)
        # normalize=True là bắt buộc — xem SPEC.md US-011 AC-1
        score = rr.compute_score([["câu hỏi thử", "đoạn văn thử"]], normalize=True)
        after = vram_reserved_gb()
        rows.append(
            ("bge-reranker-v2-m3 (fp16)", f"{after - before:.2f}", f"tổng {after:.2f}")
        )
        print(f"  +{after - before:.2f} GB (tổng {after:.2f} GB)")
        print(f"  điểm đã sigmoid: {score} — phải nằm trong [0,1]")
        notes.append(f"Điểm rerank với normalize=True: {score}")
    except Exception as e:
        rows.append(("bge-reranker-v2-m3", "LỖI", str(e)[:80]))
        notes.append(f"reranker không nạp được: {e}")

    peak_two = vram_reserved_gb()
    remaining = total_gb - peak_two
    print(f"\nSau embedding + reranker: dùng {peak_two:.2f} GB, còn {remaining:.2f} GB")

    # ── 3. Ước lượng chỗ cho LLM ────────────────────────────
    print("\n--- Chỗ còn lại cho LLM ---")
    llm_budget = remaining - 1.0  # chừa 1 GB phân mảnh + OCR nạp theo yêu cầu
    print(f"Ngân sách LLM (đã chừa 1 GB): {llm_budget:.2f} GB")
    if llm_budget >= 7.0:
        verdict = "Qwen3-8B lượng tử 4-bit (~6-7 GB) VỪA — cùng lúc với embedding+rerank"
    elif llm_budget >= 5.0:
        verdict = "Chật. Cân nhắc lượng tử sâu hơn, hoặc giải phóng embedding khi sinh"
    else:
        verdict = "KHÔNG đủ. Phải nạp/giải phóng luân phiên, hoặc dùng model nhỏ hơn"
    print(f"=> {verdict}")
    notes.append(verdict)

    # ── 4. Cảnh báo vLLM ────────────────────────────────────
    util_needed = llm_budget / total_gb
    print("\n--- Nếu dùng vLLM ---")
    print(f"gpu_memory_utilization tối đa ≈ {util_needed:.2f} (mặc định 0.90 sẽ OOM)")
    notes.append(
        f"vLLM: đặt gpu_memory_utilization <= {util_needed:.2f}; "
        "mặc định 0.90 sẽ chiếm hết và làm embedding/reranker OOM."
    )

    free_all()

    # ── Báo cáo ─────────────────────────────────────────────
    lines = [
        "# Spike S2 — ngân sách VRAM",
        "",
        f"**GPU:** {name} — {total_gb:.1f} GB",
        "",
        "| Thành phần | VRAM thêm (GB) | Ghi chú |",
        "|---|---|---|",
    ]
    lines += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    lines += [
        "",
        f"- Đỉnh sau embedding + reranker: **{peak_two:.2f} GB**",
        f"- Còn lại: **{remaining:.2f} GB** · ngân sách LLM (chừa 1 GB): **{llm_budget:.2f} GB**",
        "",
        "## Nhận định",
        "",
    ]
    lines += [f"- {n}" for n in notes]
    lines += [
        "",
        "## Việc tiếp theo",
        "",
        "1. Chạy thử LLM cục bộ thật (Ollama hoặc vLLM) SONG SONG với script "
        "này còn đang giữ model,",
        "   để đo đỉnh thật thay vì cộng ước lượng.",
        "2. Ghi quyết định runtime vào `docs/decisions/` — đây là quyết định chặn của M3 và M4.",
        "3. Cập nhật bảng ngân sách ở `SPEC-v1.md` §10.1 bằng số đo thật.",
        "4. Xác nhận PaddleOCR nạp/giải phóng được (US-057 AC-3).",
    ]

    report = OUT / "s2_vram.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nBáo cáo: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
