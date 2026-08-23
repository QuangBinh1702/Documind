"use client";

/**
 * Trình xem PDF — US-017, và là nơi US-015 thành hình.
 *
 * Vì sao PDF.js chứ không phải `<iframe>`
 * ----------------------------------------
 * Nhúng tệp vào `<iframe>` thì trình duyệt tự vẽ, rẻ hơn nhiều, và cuộn với
 * phóng to đều có sẵn. Nhưng nó là một hộp đen: không vẽ được gì lên trên, nên
 * **tô sáng đúng vùng chứa câu trả lời** — thứ phân biệt đồ án này với một
 * chatbot đọc tài liệu — không làm được.
 *
 * PDF.js vẽ ra `<canvas>`, và một lớp `<div>` phủ lên trên mang các hộp toạ độ
 * mà chunk đã lưu từ lúc nạp tài liệu.
 *
 * Vì sao vẽ từng trang một
 * -------------------------
 * US-017 AC-4 đòi trang đầu hiện ra dưới 2 giây với tài liệu 500 trang. PDF.js
 * đọc bảng mục lục của tệp rồi chỉ tải đúng trang được yêu cầu, nên chi phí
 * không phụ thuộc độ dày tài liệu. Vẽ hết mọi trang rồi mới hiện là cách chắc
 * chắn để hỏng đúng yêu cầu đó.
 *
 * Hệ toạ độ
 * ----------
 * `bbox` lưu theo hệ của PyMuPDF: điểm, gốc ở góc **trên** bên trái. Viewport
 * của PDF.js ở góc xoay 0 biến điểm PDF (gốc dưới-trái) thành
 * `((x - x0)·s, (H - y)·s)` — mà `H - y` chính là toạ độ trên-trái. Nên phép
 * đổi rút gọn còn nhân với `scale`, không cần lật gì thêm.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { GOC_API, goiTho } from "@/lib/api";

export type HopToaDo = {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

const MUC_PHONG = [0.75, 1, 1.25, 1.5, 2, 3];

export function XemPdf({
  nbId,
  sourceId,
  trang,
  hop,
}: {
  nbId: string;
  sourceId: string;
  /** Trang cần mở. Đổi giá trị này thì trình xem nhảy tới đó. */
  trang: number | null;
  /** Vùng cần tô sáng, theo hệ toạ độ trang PDF. */
  hop: HopToaDo[];
}) {
  const [tep, setTep] = useState<ArrayBuffer | null>(null);
  const [tongTrang, setTongTrang] = useState(0);
  const [trangHienTai, setTrangHienTai] = useState(1);
  const [phong, setPhong] = useState(1);
  const [loi, setLoi] = useState<string | null>(null);
  const [dangVe, setDangVe] = useState(true);
  const [kichThuoc, setKichThuoc] = useState({ rong: 0, cao: 0 });

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tepRef = useRef<unknown>(null);
  // Lượt vẽ đang chạy. Đổi trang nhanh sinh ra nhiều lượt chồng nhau, và lượt
  // cũ về sau sẽ vẽ đè lên trang mới.
  const luotVe = useRef(0);

  // ── Tải tệp ─────────────────────────────────────────
  useEffect(() => {
    let huy = false;
    setTep(null);
    setLoi(null);

    (async () => {
      try {
        const r = await goiTho(`/api/notebooks/${nbId}/sources/${sourceId}/file`);
        if (!r.ok) throw new Error(String(r.status));
        const buf = await r.arrayBuffer();
        if (!huy) setTep(buf);
      } catch {
        if (!huy) setLoi("Không mở được tệp gốc của tài liệu này.");
      }
    })();

    return () => {
      huy = true;
    };
  }, [nbId, sourceId]);

  // ── Mở tài liệu bằng PDF.js ─────────────────────────
  useEffect(() => {
    if (!tep) return;
    let huy = false;

    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        // Worker chạy ở luồng riêng: giải nén và dựng hình một trang A4 nhiều
        // chữ mất hàng trăm mili giây, và làm việc đó trên luồng chính sẽ treo
        // cả giao diện mỗi lần đổi trang.
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();

        // `tep.slice(0)` vì PDF.js **chuyển quyền sở hữu** buffer sang worker.
        // Đưa thẳng buffer gốc thì lần mở thứ hai nhận được một buffer rỗng.
        const doc = await pdfjs.getDocument({ data: tep.slice(0) }).promise;
        if (huy) return;
        tepRef.current = doc;
        setTongTrang(doc.numPages);
      } catch {
        if (!huy) setLoi("Tệp PDF này không đọc được.");
      }
    })();

    return () => {
      huy = true;
    };
  }, [tep]);

  // Trang do trích dẫn chỉ định.
  useEffect(() => {
    if (trang && trang >= 1) setTrangHienTai(trang);
  }, [trang]);

  // ── Vẽ trang hiện tại ───────────────────────────────
  const ve = useCallback(async () => {
    const doc = tepRef.current as {
      numPages: number;
      getPage: (n: number) => Promise<never>;
    } | null;
    const canvas = canvasRef.current;
    if (!doc || !canvas) return;

    const luot = ++luotVe.current;
    setDangVe(true);
    try {
      const page = (await doc.getPage(
        Math.min(Math.max(trangHienTai, 1), doc.numPages),
      )) as unknown as {
        getViewport: (o: { scale: number }) => { width: number; height: number };
        render: (o: object) => { promise: Promise<void>; cancel: () => void };
      };
      if (luot !== luotVe.current) return;

      // Nhân với tỉ lệ điểm ảnh của màn hình rồi thu lại bằng CSS: không có
      // bước này thì chữ trên màn hình HiDPI nhoè hẳn.
      const dpr = window.devicePixelRatio || 1;
      const viewport = page.getViewport({ scale: phong });
      canvas.width = Math.floor(viewport.width * dpr);
      canvas.height = Math.floor(viewport.height * dpr);
      setKichThuoc({ rong: viewport.width, cao: viewport.height });

      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      await page.render({ canvas, canvasContext: ctx, viewport }).promise;
    } catch {
      /* lượt vẽ bị huỷ khi đổi trang — không phải lỗi */
    } finally {
      if (luot === luotVe.current) setDangVe(false);
    }
  }, [trangHienTai, phong]);

  useEffect(() => {
    void ve();
  }, [ve, tongTrang]);

  if (loi) return <p className="p-4 text-sm text-canh-bao">{loi}</p>;

  const hopTrangNay = hop.filter((h) => h.page === trangHienTai);

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-vien px-3 py-2 text-xs">
        <button
          onClick={() => setTrangHienTai((t) => Math.max(1, t - 1))}
          disabled={trangHienTai <= 1}
          className="rounded border border-vien px-2 py-1 text-mo disabled:opacity-40"
        >
          ‹
        </button>
        <span className="tabular-nums text-mo">
          {trangHienTai}/{tongTrang || "…"}
        </span>
        <button
          onClick={() => setTrangHienTai((t) => Math.min(tongTrang || t, t + 1))}
          disabled={!tongTrang || trangHienTai >= tongTrang}
          className="rounded border border-vien px-2 py-1 text-mo disabled:opacity-40"
        >
          ›
        </button>

        <select
          value={phong}
          onChange={(e) => setPhong(Number(e.target.value))}
          aria-label="Mức phóng"
          className="ml-auto rounded border border-vien bg-the px-1.5 py-1 text-mo"
        >
          {MUC_PHONG.map((m) => (
            <option key={m} value={m}>
              {Math.round(m * 100)}%
            </option>
          ))}
        </select>
      </div>

      <div className="min-h-0 flex-1 overflow-auto bg-nen p-3">
        <div
          className="relative mx-auto shadow-sm"
          style={{ width: kichThuoc.rong || undefined, height: kichThuoc.cao || undefined }}
        >
          <canvas
            ref={canvasRef}
            style={{ width: kichThuoc.rong, height: kichThuoc.cao }}
            className="block bg-white"
          />

          {/* Lớp tô sáng — US-015. `pointer-events-none` để không chặn việc bôi
              đen chữ trên canvas bên dưới. */}
          {hopTrangNay.map((h, i) => (
            <div
              key={i}
              className="pointer-events-none absolute rounded-[2px]"
              style={{
                left: h.x0 * phong,
                top: h.y0 * phong,
                width: (h.x1 - h.x0) * phong,
                height: (h.y1 - h.y0) * phong,
                background: "var(--to-sang)",
                boxShadow: "inset 0 0 0 1px var(--to-sang-vien)",
                mixBlendMode: "multiply",
              }}
            />
          ))}

          {dangVe && (
            <div className="absolute inset-0 grid place-items-center bg-nen/60 text-xs text-mo">
              đang dựng trang…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Đường tải tệp gốc — dùng chung với chỗ hiển thị ảnh. */
export function duongTep(nbId: string, sourceId: string): string {
  return `${GOC_API}/api/notebooks/${nbId}/sources/${sourceId}/file`;
}
