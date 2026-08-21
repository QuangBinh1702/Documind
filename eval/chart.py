"""Vẽ biểu đồ ra SVG — US-046 AC-4, US-047 AC-3.

Vì sao tự vẽ thay vì dùng matplotlib
-------------------------------------
Hai biểu đồ này đi thẳng vào báo cáo, và cả hai đều đơn giản: một biểu đồ cột so
sánh vài cấu hình, một biểu đồ đường ba dãy số. Kéo về một thư viện vẽ đồ thị
đầy đủ cho ngần ấy việc là thêm một phụ thuộc nặng vào một dự án vốn đã phải cân
nhắc từng gói vì ràng buộc VRAM.

SVG cũng hợp hơn cho mục đích ở đây: nó là ảnh vector, phóng to trong Word hay
LaTeX không vỡ, và sửa được bằng trình soạn thảo văn bản khi cần đổi một nhãn
lúc gần nộp.

Không có phụ thuộc nào ngoài thư viện chuẩn.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

__all__ = ["bar_chart", "line_chart"]

# Bảng màu giữ được sự phân biệt khi in đen trắng — báo cáo in ra giấy vẫn đọc
# được, và người không phân biệt được màu vẫn theo dõi được.
MAU = ["#2563eb", "#dc2626", "#16a34a", "#ca8a04", "#9333ea", "#0891b2"]

FONT = "font-family='Segoe UI, system-ui, sans-serif'"


def _khung(rong: int, cao: int, tieu_de: str, body: str) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{rong}' height='{cao}' "
        f"viewBox='0 0 {rong} {cao}' {FONT}>"
        f"<rect width='{rong}' height='{cao}' fill='white'/>"
        f"<text x='{rong // 2}' y='26' text-anchor='middle' font-size='15' "
        f"font-weight='600'>{escape(tieu_de)}</text>"
        f"{body}</svg>"
    )


def bar_chart(
    path: Path,
    *,
    tieu_de: str,
    nhom: list[str],
    day: list[tuple[str, list[float]]],
    truc_y: str = "",
    y_max: float | None = None,
) -> Path:
    """Biểu đồ cột nhóm.

    `nhom` là nhãn trục X (ví dụ các cấu hình A–F); `day` là các dãy số, mỗi dãy
    một chỉ số, mỗi dãy phải có đúng `len(nhom)` giá trị.
    """
    for ten, gia_tri in day:
        if len(gia_tri) != len(nhom):
            raise ValueError(f"Dãy '{ten}' có {len(gia_tri)} giá trị, cần {len(nhom)}")

    le_trai, le_phai, le_tren, le_duoi = 62, 20, 52, 76
    rong_ve, cao_ve = max(90 * len(nhom), 420), 300
    rong = le_trai + rong_ve + le_phai
    cao = le_tren + cao_ve + le_duoi

    dinh = y_max or max((max(v) for _, v in day if v), default=1.0)
    dinh = dinh * 1.12 or 1.0

    out: list[str] = []

    # Lưới ngang và nhãn trục Y.
    for i in range(6):
        y = le_tren + cao_ve - cao_ve * i / 5
        gt = dinh * i / 5
        out.append(
            f"<line x1='{le_trai}' y1='{y:.1f}' x2='{le_trai + rong_ve}' y2='{y:.1f}' "
            f"stroke='#e5e7eb' stroke-width='1'/>"
            f"<text x='{le_trai - 8}' y='{y + 4:.1f}' text-anchor='end' font-size='11' "
            f"fill='#6b7280'>{gt:.2f}</text>"
        )

    rong_nhom = rong_ve / len(nhom)
    rong_cot = rong_nhom * 0.72 / max(len(day), 1)

    for i, ten_nhom in enumerate(nhom):
        goc = le_trai + i * rong_nhom + rong_nhom * 0.14
        for j, (_, gia_tri) in enumerate(day):
            v = gia_tri[i]
            h = cao_ve * (v / dinh) if dinh else 0
            x = goc + j * rong_cot
            y = le_tren + cao_ve - h
            out.append(
                f"<rect x='{x:.1f}' y='{y:.1f}' width='{rong_cot - 2:.1f}' "
                f"height='{h:.1f}' fill='{MAU[j % len(MAU)]}'/>"
                f"<text x='{x + rong_cot / 2 - 1:.1f}' y='{y - 4:.1f}' "
                f"text-anchor='middle' font-size='9' fill='#374151'>{v:.2f}</text>"
            )
        out.append(
            f"<text x='{le_trai + i * rong_nhom + rong_nhom / 2:.1f}' "
            f"y='{le_tren + cao_ve + 18}' text-anchor='middle' font-size='12'>"
            f"{escape(ten_nhom)}</text>"
        )

    out.append(
        f"<line x1='{le_trai}' y1='{le_tren + cao_ve}' x2='{le_trai + rong_ve}' "
        f"y2='{le_tren + cao_ve}' stroke='#374151' stroke-width='1.5'/>"
    )
    if truc_y:
        out.append(
            f"<text x='16' y='{le_tren + cao_ve / 2}' font-size='11' fill='#6b7280' "
            f"transform='rotate(-90 16 {le_tren + cao_ve / 2})' text-anchor='middle'>"
            f"{escape(truc_y)}</text>"
        )

    out.append(_chu_giai(day, le_trai, le_tren + cao_ve + 42))
    path.write_text(_khung(rong, cao, tieu_de, "".join(out)), encoding="utf-8")
    return path


def line_chart(
    path: Path,
    *,
    tieu_de: str,
    x: list[float],
    day: list[tuple[str, list[float]]],
    truc_x: str = "",
    danh_dau: float | None = None,
    nhan_danh_dau: str = "",
) -> Path:
    """Biểu đồ đường. `danh_dau` vẽ một đường dọc — dùng để chỉ giá trị đã chọn."""
    le_trai, le_phai, le_tren, le_duoi = 62, 24, 52, 76
    rong_ve, cao_ve = 560, 300
    rong = le_trai + rong_ve + le_phai
    cao = le_tren + cao_ve + le_duoi

    x_min, x_max = min(x), max(x)
    khoang_x = (x_max - x_min) or 1.0

    def toa_do(xi: float, yi: float) -> tuple[float, float]:
        return (
            le_trai + rong_ve * (xi - x_min) / khoang_x,
            le_tren + cao_ve - cao_ve * yi,
        )

    out: list[str] = []
    for i in range(6):
        y = le_tren + cao_ve - cao_ve * i / 5
        out.append(
            f"<line x1='{le_trai}' y1='{y:.1f}' x2='{le_trai + rong_ve}' y2='{y:.1f}' "
            f"stroke='#e5e7eb'/>"
            f"<text x='{le_trai - 8}' y='{y + 4:.1f}' text-anchor='end' font-size='11' "
            f"fill='#6b7280'>{i / 5:.1f}</text>"
        )

    if danh_dau is not None:
        dx, _ = toa_do(danh_dau, 0)
        out.append(
            f"<line x1='{dx:.1f}' y1='{le_tren}' x2='{dx:.1f}' "
            f"y2='{le_tren + cao_ve}' stroke='#111827' stroke-width='1.5' "
            f"stroke-dasharray='5 4'/>"
            f"<text x='{dx + 6:.1f}' y='{le_tren + 14}' font-size='11' "
            f"fill='#111827'>{escape(nhan_danh_dau)}</text>"
        )

    for j, (_, gia_tri) in enumerate(day):
        diem = " ".join(f"{cx:.1f},{cy:.1f}" for cx, cy in
                        (toa_do(xi, yi) for xi, yi in zip(x, gia_tri, strict=True)))
        out.append(
            f"<polyline points='{diem}' fill='none' stroke='{MAU[j % len(MAU)]}' "
            f"stroke-width='2'/>"
        )
        for xi, yi in zip(x, gia_tri, strict=True):
            cx, cy = toa_do(xi, yi)
            out.append(f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='2.5' "
                       f"fill='{MAU[j % len(MAU)]}'/>")

    for xi in x:
        cx, _ = toa_do(xi, 0)
        out.append(
            f"<text x='{cx:.1f}' y='{le_tren + cao_ve + 18}' text-anchor='middle' "
            f"font-size='10'>{xi:g}</text>"
        )

    out.append(
        f"<line x1='{le_trai}' y1='{le_tren + cao_ve}' x2='{le_trai + rong_ve}' "
        f"y2='{le_tren + cao_ve}' stroke='#374151' stroke-width='1.5'/>"
    )
    if truc_x:
        out.append(
            f"<text x='{le_trai + rong_ve / 2}' y='{le_tren + cao_ve + 36}' "
            f"text-anchor='middle' font-size='11' fill='#6b7280'>{escape(truc_x)}</text>"
        )

    out.append(_chu_giai(day, le_trai, le_tren + cao_ve + 54))
    path.write_text(_khung(rong, cao, tieu_de, "".join(out)), encoding="utf-8")
    return path


def _chu_giai(day: list[tuple[str, list[float]]], x0: int, y: int) -> str:
    ra: list[str] = []
    x = x0
    for j, (ten, _) in enumerate(day):
        ra.append(
            f"<rect x='{x}' y='{y - 9}' width='11' height='11' "
            f"fill='{MAU[j % len(MAU)]}'/>"
            f"<text x='{x + 16}' y='{y}' font-size='11.5'>{escape(ten)}</text>"
        )
        x += 22 + len(ten) * 7
    return "".join(ra)
