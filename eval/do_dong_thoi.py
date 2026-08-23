"""Đo tải đồng thời — US-067.

Câu hỏi cần trả lời rất cụ thể: *"mở năm tab cùng hỏi thì hệ thống có sập
không, và chậm đi bao nhiêu?"* Buổi bảo vệ sẽ có người mở tab thứ hai.

Cách đo
-------
Hai lượt trên **cùng một bộ câu hỏi**, để chênh lệch duy nhất là mức đồng thời:

1. **Tuần tự** — từng câu một. Đây là đường cơ sở.
2. **Đồng thời** — N câu cùng lúc.

So p95 của hai lượt. AC-2 đòi p95 đồng thời ≤ 2× p95 tuần tự.

Vì sao đo qua API thật, không gọi thẳng hàm
--------------------------------------------
Gọi thẳng `answer_question` bỏ qua đúng những thứ đang được đo: vòng đời phiên
cơ sở dữ liệu, `asyncio.to_thread` đẩy phần chặn CPU ra khỏi vòng lặp sự kiện,
và pool kết nối. Một phép đo bỏ qua chúng sẽ đẹp và sai.

Đọc kết quả cho đúng
---------------------
Con số phụ thuộc **máy đang chạy**. Đo trên laptop CPU cho biết hệ thống không
đổ vỡ; nó **không** thay được số đo trên máy đích 16 GB VRAM, và báo cáo phải
ghi rõ đo ở đâu (AC-4).

    python eval/do_dong_thoi.py
    python eval/do_dong_thoi.py --dong-thoi 10 --so-cau 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

QUESTIONS = ROOT / "eval" / "dataset" / "questions.json"
RESULTS = ROOT / "eval" / "results"

GOC_API = "http://localhost:8000"


@dataclass(frozen=True, slots=True)
class Luot:
    id: str
    giay: float
    ok: bool
    loi: str = ""


async def _hoi(client, cau_hoi: str, notebook_id: str, ma: str) -> Luot:
    """Một lượt hỏi trọn vẹn, đo tới sự kiện `done`.

    Đo tới `done` chứ không tới token đầu tiên: token đầu tới sớm và nó che mất
    phần đắt nhất. Người dùng đợi tới lúc câu trả lời xong.
    """
    bat_dau = time.perf_counter()
    try:
        async with client.stream(
            "POST",
            f"{GOC_API}/api/chat/ask",
            json={"question": cau_hoi, "notebook_id": notebook_id},
            timeout=300.0,
        ) as r:
            if r.status_code != 200:
                return Luot(ma, time.perf_counter() - bat_dau, False,
                            f"HTTP {r.status_code}")
            xong = False
            async for dong in r.aiter_lines():
                if not dong.startswith("data: "):
                    continue
                su_kien = json.loads(dong[6:])
                if su_kien["type"] == "error":
                    return Luot(ma, time.perf_counter() - bat_dau, False,
                                str(su_kien.get("message", "")))
                if su_kien["type"] == "done":
                    xong = True
            return Luot(ma, time.perf_counter() - bat_dau, xong,
                        "" if xong else "luồng kết thúc mà không có 'done'")
    except Exception as exc:
        return Luot(ma, time.perf_counter() - bat_dau, False, f"{type(exc).__name__}: {exc}")


def _p95(gia_tri: list[float]) -> float:
    """Phân vị 95, lấy giá trị CÓ THẬT trong tập mẫu.

    Không nội suy: với cỡ mẫu vài chục, nội suy tạo ra một con số chưa từng xảy
    ra, và một con số đã từng thật sự xảy ra thì dễ bảo vệ hơn.
    """
    if not gia_tri:
        return 0.0
    sap = sorted(gia_tri)
    vi_tri = max(0, min(len(sap) - 1, round(0.95 * len(sap)) - 1))
    return sap[vi_tri]


def _tom_tat(ten: str, luot: list[Luot]) -> dict:
    ok = [x for x in luot if x.ok]
    giay = [x.giay for x in ok]
    return {
        "ten": ten,
        "tong": len(luot),
        "thanh_cong": len(ok),
        "that_bai": len(luot) - len(ok),
        "trung_binh": statistics.mean(giay) if giay else 0.0,
        "trung_vi": statistics.median(giay) if giay else 0.0,
        "p95": _p95(giay),
        "nhanh_nhat": min(giay) if giay else 0.0,
        "cham_nhat": max(giay) if giay else 0.0,
    }


def _in(t: dict) -> None:
    print(f"  {t['ten']}")
    print(f"    thành công    {t['thanh_cong']}/{t['tong']}")
    if t["that_bai"]:
        print(f"    THẤT BẠI      {t['that_bai']}")
    print(f"    trung bình    {t['trung_binh']:.2f}s")
    print(f"    trung vị      {t['trung_vi']:.2f}s")
    print(f"    p95           {t['p95']:.2f}s")
    print(f"    nhanh / chậm  {t['nhanh_nhat']:.2f}s / {t['cham_nhat']:.2f}s")


async def chay(so_cau: int, dong_thoi: int) -> int:
    try:
        import httpx
    except ImportError:
        print("Thiếu httpx. Cài bằng: pip install httpx")
        return 1

    if not QUESTIONS.exists():
        print(f"Chưa có bộ câu hỏi ở {QUESTIONS.relative_to(ROOT)}.")
        print("Chạy `python eval/build_dataset.py` trước.")
        return 1

    du_lieu = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    muc = du_lieu.get("questions", du_lieu) if isinstance(du_lieu, dict) else du_lieu
    trong_pham_vi = [m for m in muc if m.get("in_scope", True)][:so_cau]
    if not trong_pham_vi:
        print("Bộ câu hỏi không có câu nào trong phạm vi.")
        return 1

    async with httpx.AsyncClient() as client:
        # Đăng nhập một lần; mọi lượt dùng chung token.
        thong_tin = await _dang_nhap(client)
        if thong_tin is None:
            return 1
        token, notebook_id = thong_tin
        client.headers["Authorization"] = f"Bearer {token}"

        print(f"\n{len(trong_pham_vi)} câu hỏi · notebook {notebook_id}\n")

        # ── Làm nóng ───────────────────────────────────
        #
        # Lượt đầu tiên phải nạp mô hình vào bộ nhớ. Tính nó vào đường cơ sở sẽ
        # làm đường cơ sở chậm giả, và tỉ lệ so sánh đẹp giả theo.
        print("Làm nóng (nạp mô hình) …")
        khoi_dong = await _hoi(client, trong_pham_vi[0]["question"], notebook_id, "warmup")
        print(f"  {khoi_dong.giay:.2f}s\n")

        print("Lượt 1 — tuần tự (đường cơ sở)")
        tuan_tu: list[Luot] = []
        for i, m in enumerate(trong_pham_vi, start=1):
            tuan_tu.append(await _hoi(client, m["question"], notebook_id, m.get("id", str(i))))
            print(f"  {i}/{len(trong_pham_vi)}  {tuan_tu[-1].giay:.2f}s", end="\r")
        print(" " * 40, end="\r")

        print(f"\nLượt 2 — {dong_thoi} câu cùng lúc")
        gioi_han = asyncio.Semaphore(dong_thoi)

        async def co_gioi_han(m: dict, i: int) -> Luot:
            async with gioi_han:
                return await _hoi(client, m["question"], notebook_id, m.get("id", str(i)))

        bat_dau = time.perf_counter()
        song_song = await asyncio.gather(
            *(co_gioi_han(m, i) for i, m in enumerate(trong_pham_vi, start=1))
        )
        tong_giay = time.perf_counter() - bat_dau

    t1 = _tom_tat("tuần tự", tuan_tu)
    t2 = _tom_tat(f"{dong_thoi} đồng thời", list(song_song))

    print("\n" + "=" * 52)
    _in(t1)
    print()
    _in(t2)
    print(f"    tổng thời gian tường  {tong_giay:.2f}s")
    print("=" * 52)

    ty_le = t2["p95"] / t1["p95"] if t1["p95"] else 0.0
    print(f"\np95 đồng thời / p95 tuần tự = {ty_le:.2f}×")

    dat_ac1 = t2["that_bai"] == 0
    dat_ac2 = ty_le <= 2.0
    print(f"  AC-1 mọi truy vấn trả về kết quả : {'ĐẠT' if dat_ac1 else 'KHÔNG ĐẠT'}")
    print(f"  AC-2 p95 ≤ 2× đường cơ sở        : {'ĐẠT' if dat_ac2 else 'KHÔNG ĐẠT'}")

    if not dat_ac1:
        print("\n  Những lượt hỏng:")
        for x in song_song:
            if not x.ok:
                print(f"    {x.id}: {x.loi}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    ra = RESULTS / "dong-thoi.json"
    ra.write_text(
        json.dumps(
            {
                "luc": datetime.now(UTC).isoformat(timespec="seconds"),
                "so_cau": len(trong_pham_vi),
                "muc_dong_thoi": dong_thoi,
                "tuan_tu": t1,
                "dong_thoi": t2,
                "ty_le_p95": ty_le,
                "tong_giay_dong_thoi": tong_giay,
                "dat_ac1": dat_ac1,
                "dat_ac2": dat_ac2,
                # Con số vô nghĩa nếu không biết đo trên máy nào (AC-4).
                "may": _mo_ta_may(),
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nKết quả: {ra.relative_to(ROOT)}")
    print("Báo cáo phải ghi rõ phép đo này chạy trên phần cứng nào (AC-4).")
    return 0 if (dat_ac1 and dat_ac2) else 1


def _mo_ta_may() -> dict:
    """Ghi lại đủ để biết con số này đo ở đâu."""
    import platform

    from app.settings import settings

    mo_ta = {
        "he_dieu_hanh": platform.platform(),
        "python": platform.python_version(),
        "device": settings.device,
        "embedding_model": settings.embedding_model,
        "rerank_candidates": settings.rerank_candidates,
        "default_mode": settings.default_mode,
    }
    try:
        import torch

        mo_ta["cuda"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            mo_ta["gpu"] = torch.cuda.get_device_name(0)
            mo_ta["vram_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / 1024**3, 1
            )
    except ImportError:
        mo_ta["cuda"] = False
    return mo_ta


async def _dang_nhap(client) -> tuple[str, str] | None:
    """Lấy token và một notebook đã có tài liệu sẵn sàng."""
    import os

    email = os.environ.get("EVAL_EMAIL")
    mat_khau = os.environ.get("EVAL_PASSWORD")
    if not email or not mat_khau:
        print(
            "Cần EVAL_EMAIL và EVAL_PASSWORD của một tài khoản đã có notebook\n"
            "chứa tài liệu đã xử lý xong. Ví dụ:\n\n"
            "    set EVAL_EMAIL=ban@example.com\n"
            "    set EVAL_PASSWORD=...\n"
        )
        return None

    r = await client.post(
        f"{GOC_API}/api/auth/login", json={"email": email, "password": mat_khau}
    )
    if r.status_code != 200:
        print(f"Đăng nhập thất bại: {r.status_code} {r.text[:200]}")
        return None
    token = r.json()["access_token"]

    ds = await client.get(
        f"{GOC_API}/api/notebooks", headers={"Authorization": f"Bearer {token}"}
    )
    notebooks = [n for n in ds.json() if n["ready_count"] > 0]
    if not notebooks:
        print("Tài khoản này chưa có notebook nào với tài liệu đã xử lý xong.")
        return None

    return token, notebooks[0]["id"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--so-cau", type=int, default=10,
                        help="số câu hỏi dùng cho mỗi lượt (mặc định 10)")
    parser.add_argument("--dong-thoi", type=int, default=5,
                        help="số truy vấn chạy cùng lúc (mặc định 5 — AC-1)")
    args = parser.parse_args()
    return asyncio.run(chay(args.so_cau, args.dong_thoi))


if __name__ == "__main__":
    raise SystemExit(main())
