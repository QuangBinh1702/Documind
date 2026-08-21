"""Spike S3 — bbox từ PyMuPDF có vẽ đúng chỗ trên PDF.js không?

Câu hỏi: lấy toạ độ của một đoạn văn bằng PyMuPDF rồi vẽ overlay trên PDF.js,
highlight có nằm đúng chỗ không — kể cả khi zoom?

Quyết định phụ thuộc: US-015 dừng ở bậc nào trong thang giảm cấp (SPEC.md AC-5).
Đây là story rủi ro cao nhất của đồ án.

    Bậc 1 — highlight theo bbox chính xác        <- spike này kiểm chứng
    Bậc 2 — nhảy đúng trang + tìm chuỗi snippet trong text layer
    Bậc 3 — nhảy đúng trang + hiện snippet ở khung bên

Điểm mấu chốt kỹ thuật: PyMuPDF dùng hệ toạ độ điểm (72 dpi), gốc ở GÓC TRÊN
BÊN TRÁI. PDF.js vẽ theo CSS pixel đã nhân với `scale` của viewport. Phép quy
đổi là: css = pdf_point * scale. Nếu trang có /Rotate hoặc CropBox lệch
MediaBox thì phải xử lý thêm — spike sẽ cảnh báo khi gặp.

Chạy:  python spikes/s3_highlight.py "cụm từ cần tìm"
Kết quả: spikes/out/s3_highlight.html  — mở bằng trình duyệt
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("Thiếu PyMuPDF. Chạy: pip install -r spikes/requirements.txt")

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
OUT = ROOT / "out"

PDFJS_CDN = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379"


def find_pdf() -> Path | None:
    for name in ("text.pdf", "sample.pdf"):
        p = SAMPLES / name
        if p.exists():
            return p
    pdfs = sorted(SAMPLES.glob("*.pdf"))
    return pdfs[0] if pdfs else None


def locate(pdf: Path, needle: str) -> tuple[list[dict], list[str]]:
    """Tìm needle trong PDF, trả về danh sách bbox theo hệ toạ độ PDF."""
    doc = fitz.open(pdf)
    hits: list[dict] = []
    warnings: list[str] = []

    for pno in range(len(doc)):
        page = doc[pno]

        if page.rotation:
            warnings.append(
                f"Trang {pno + 1} có /Rotate = {page.rotation}° — "
                "phép quy đổi toạ độ phải xoay theo, spike này chưa xử lý."
            )
        if page.cropbox != page.mediabox:
            warnings.append(
                f"Trang {pno + 1} có CropBox khác MediaBox — "
                "gốc toạ độ lệch, phải trừ cropbox.x0/y0."
            )

        rects = page.search_for(needle)
        for r in rects:
            hits.append(
                {
                    "page": pno + 1,
                    "x0": round(r.x0, 2),
                    "y0": round(r.y0, 2),
                    "x1": round(r.x1, 2),
                    "y1": round(r.y1, 2),
                    "page_w": round(page.rect.width, 2),
                    "page_h": round(page.rect.height, 2),
                }
            )

    doc.close()
    return hits, warnings


HTML = """<!doctype html>
<meta charset="utf-8">
<title>Spike S3 — kiểm chứng highlight theo bbox</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0; padding: 24px;
         background: Canvas; color: CanvasText; }}
  h1 {{ font-size: 18px; margin: 0 0 4px; }}
  .meta {{ opacity: .75; font-size: 13px; margin-bottom: 16px; }}
  .bar {{ display: flex; gap: 12px; align-items: center; margin-bottom: 16px;
          flex-wrap: wrap; }}
  button {{ font: inherit; padding: 6px 12px; cursor: pointer; }}
  .wrap {{ position: relative; display: inline-block;
           box-shadow: 0 2px 12px rgb(0 0 0 / .25); }}
  canvas {{ display: block; }}
  .layer {{ position: absolute; inset: 0; pointer-events: none; }}
  .hl {{ position: absolute; background: rgb(255 214 0 / .42);
         outline: 1.5px solid rgb(220 150 0 / .9); border-radius: 2px; }}
  .warn {{ background: rgb(255 180 0 / .18); border-left: 3px solid orange;
           padding: 8px 12px; margin-bottom: 16px; font-size: 13px; }}
  code {{ background: rgb(128 128 128 / .18); padding: 1px 5px; border-radius: 3px; }}
</style>

<h1>Spike S3 — highlight theo bbox</h1>
<div class="meta">
  Tệp <code>{pdf_name}</code> · tìm <code>{needle}</code> ·
  <strong>{n_hits}</strong> kết quả
</div>

{warn_html}

<div class="bar">
  <button onclick="setScale(scale / 1.25)">−</button>
  <span>zoom <span id="z">150</span>%</span>
  <button onclick="setScale(scale * 1.25)">+</button>
  <span style="opacity:.7">|</span>
  <button onclick="go(-1)">◀ trang trước</button>
  <span>trang <span id="p">1</span> / <span id="np">?</span></span>
  <button onclick="go(1)">trang sau ▶</button>
</div>

<div class="wrap">
  <canvas id="c"></canvas>
  <div class="layer" id="layer"></div>
</div>

<p style="margin-top:20px;max-width:60ch;opacity:.8">
  <strong>Cách đọc kết quả.</strong> Nếu ô vàng phủ đúng cụm từ ở mọi mức zoom,
  <strong>Bậc 1 khả thi</strong> — highlight theo bbox chính xác dựng được.
  Nếu ô lệch cố định thì sai gốc toạ độ; nếu lệch tăng dần theo zoom thì sai
  hệ số scale; nếu lệch chỉ ở vài trang thì xem cảnh báo /Rotate và CropBox
  bên trên.
</p>

<script src="{cdn}/pdf.min.js"></script>
<script>
pdfjsLib.GlobalWorkerOptions.workerSrc = "{cdn}/pdf.worker.min.js";

const HITS = {hits_json};
let scale = 1.5, pageNum = {first_page}, pdfDoc = null;

async function render() {{
  const page = await pdfDoc.getPage(pageNum);
  const vp = page.getViewport({{ scale }});
  const canvas = document.getElementById("c");
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;

  canvas.width = Math.floor(vp.width * dpr);
  canvas.height = Math.floor(vp.height * dpr);
  canvas.style.width = vp.width + "px";
  canvas.style.height = vp.height + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  await page.render({{ canvasContext: ctx, viewport: vp }}).promise;

  // Quy đổi bbox: toạ độ PDF (điểm, gốc trên-trái) -> CSS pixel.
  // Chỉ cần nhân scale — PyMuPDF đã trả về gốc trên-trái giống PDF.js.
  const layer = document.getElementById("layer");
  layer.innerHTML = "";
  layer.style.width = vp.width + "px";
  layer.style.height = vp.height + "px";

  for (const h of HITS.filter(h => h.page === pageNum)) {{
    const d = document.createElement("div");
    d.className = "hl";
    d.style.left   = (h.x0 * scale) + "px";
    d.style.top    = (h.y0 * scale) + "px";
    d.style.width  = ((h.x1 - h.x0) * scale) + "px";
    d.style.height = ((h.y1 - h.y0) * scale) + "px";
    layer.appendChild(d);
  }}

  document.getElementById("p").textContent = pageNum;
  document.getElementById("z").textContent = Math.round(scale / 1.5 * 100);
}}

function setScale(s) {{ scale = Math.max(0.4, Math.min(5, s)); render(); }}
function go(d) {{
  const n = pageNum + d;
  if (n >= 1 && n <= pdfDoc.numPages) {{ pageNum = n; render(); }}
}}

pdfjsLib.getDocument("{pdf_file}").promise.then(doc => {{
  pdfDoc = doc;
  document.getElementById("np").textContent = doc.numPages;
  render();
}});
</script>
"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    needle = sys.argv[1] if len(sys.argv) > 1 else "quy định"

    pdf = find_pdf()
    if pdf is None:
        print(f"Không tìm thấy PDF trong {SAMPLES}")
        print("Đặt một PDF tiếng Việt CÓ LỚP TEXT vào đó rồi chạy lại.")
        return 1

    print(f"Tệp: {pdf.name}")
    print(f"Tìm: {needle!r}")

    hits, warnings = locate(pdf, needle)
    print(f"Tìm thấy {len(hits)} kết quả")

    if not hits:
        print("\nKhông có kết quả nào. Thử cụm từ khác:")
        print(f'  python spikes/s3_highlight.py "cụm từ có thật trong tệp"')
        return 1

    for w in dict.fromkeys(warnings):
        print(f"  [!] {w}")

    for h in hits[:5]:
        print(
            f"  trang {h['page']}: ({h['x0']}, {h['y0']}) → ({h['x1']}, {h['y1']}) "
            f"trên khổ {h['page_w']}×{h['page_h']}"
        )

    shutil.copy(pdf, OUT / pdf.name)

    warn_html = ""
    if warnings:
        items = "".join(f"<div>{w}</div>" for w in dict.fromkeys(warnings))
        warn_html = f'<div class="warn"><strong>Cảnh báo toạ độ</strong>{items}</div>'

    html = HTML.format(
        pdf_name=pdf.name,
        pdf_file=pdf.name,
        needle=needle,
        n_hits=len(hits),
        hits_json=json.dumps(hits, ensure_ascii=False),
        first_page=hits[0]["page"],
        cdn=PDFJS_CDN,
        warn_html=warn_html,
    )

    report = OUT / "s3_highlight.html"
    report.write_text(html, encoding="utf-8")

    print(f"\nMở tệp này bằng trình duyệt: {report}")
    print("Kiểm tra: ô vàng có phủ đúng cụm từ không, ở MỌI mức zoom?")
    print("  - đúng ở mọi zoom      -> Bậc 1 khả thi, US-015 làm được như thiết kế")
    print("  - lệch cố định         -> sai gốc toạ độ (CropBox?)")
    print("  - lệch tăng theo zoom  -> sai hệ số scale")
    print("  - lệch vài trang       -> xem cảnh báo /Rotate bên trên")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
