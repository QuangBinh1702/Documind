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
 *
 * Vừa bề ngang, và vì sao nó là mặc định
 * ---------------------------------------
 * Trước đây trình xem mở ở 100% và neo trang ở góc trên bên trái. Với một cột
 * hẹp thì đó là cách chắc chắn để người dùng bấm một chip trích dẫn và nhìn vào
 * một khoảng lề trắng — đoạn được tô sáng nằm ngoài khung nhìn, và không có gì
 * nói cho họ biết phải cuộn đi đâu. Nên mặc định là vừa bề ngang cột, và sau
 * mỗi lượt vẽ, vùng tô sáng được cuộn vào giữa khung.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { HopToaDo, NguonXem } from "@/lib/nguonXem";
import { Bt } from "@/components/BieuTuong";
import { useNgonNgu } from "@/components/NgonNguProvider";

export type { HopToaDo };

/** `null` là "vừa bề ngang" — tính lại mỗi lần cột đổi kích thước. */
const MUC_PHONG: (number | null)[] = [null, 0.75, 1, 1.25, 1.5, 2, 3];

export function XemPdf({
  nguon,
  sourceId,
  trang,
  hop,
  onKhongMoDuoc,
}: {
  nguon: NguonXem;
  sourceId: string;
  /** Trang cần mở. Đổi giá trị này thì trình xem nhảy tới đó. */
  trang: number | null;
  /** Vùng cần tô sáng, theo hệ toạ độ trang PDF. */
  hop: HopToaDo[];
  /**
   * Tệp gốc không lấy được. Chỗ gọi lùi về hiện nguyên văn đoạn trích, thay vì
   * để lại một khung trống kèm một câu báo lỗi — người dùng bấm chip là để đọc
   * một đoạn văn, và đoạn văn ấy vẫn còn, chỉ là trang giấy quanh nó thì không.
   */
  onKhongMoDuoc?: () => void;
}) {
  const [tep, setTep] = useState<ArrayBuffer | null>(null);
  const [tongTrang, setTongTrang] = useState(0);
  const [trangHienTai, setTrangHienTai] = useState(1);
  const [phong, setPhong] = useState<number | null>(null);
  const [phongThat, setPhongThat] = useState(1);
  const [loi, setLoi] = useState<string | null>(null);
  const [dangVe, setDangVe] = useState(true);
  const [kichThuoc, setKichThuoc] = useState({ rong: 0, cao: 0 });
  const { t } = useNgonNgu();

  const khungRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tepRef = useRef<unknown>(null);
  // Lượt vẽ đang chạy. Đổi trang nhanh sinh ra nhiều lượt chồng nhau, và lượt
  // cũ về sau sẽ vẽ đè lên trang mới.
  const luotVe = useRef(0);
  // Bề ngang khung nhìn, để tính mức "vừa bề ngang".
  const [beNgang, setBeNgang] = useState(0);

  // ── Tải tệp ─────────────────────────────────────────
  useEffect(() => {
    let huy = false;
    setTep(null);
    setLoi(null);

    (async () => {
      try {
        const r = await nguon.tep(sourceId);
        if (!r.ok) throw new Error(String(r.status));
        const buf = await r.arrayBuffer();
        if (!huy) setTep(buf);
      } catch {
        if (huy) return;
        setLoi(t("xem.khongMoDuoc"));
        onKhongMoDuoc?.();
      }
    })();

    return () => {
      huy = true;
    };
  }, [nguon, sourceId, onKhongMoDuoc]);

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
        if (!huy) setLoi(t("xem.khongDocDuocPdf"));
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

  // Bề ngang khung nhìn — đổi khi kéo đường phân cách giữa các cột.
  useEffect(() => {
    const el = khungRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setBeNgang(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  /** Cuộn vùng tô sáng vào giữa khung, hoặc về đầu trang nếu trang này không có. */
  const veDoanTrich = useCallback(() => {
    const khung = khungRef.current;
    if (!khung) return;
    const cua_trang = hop.filter((h) => h.page === trangHienTai);
    if (cua_trang.length === 0) {
      khung.scrollTo({ top: 0, left: 0, behavior: "smooth" });
      return;
    }
    const dinh = Math.min(...cua_trang.map((h) => h.y0)) * phongThat;
    const trai = Math.min(...cua_trang.map((h) => h.x0)) * phongThat;
    khung.scrollTo({
      // Chừa lại một phần khung phía trên: đoạn được trích dán sát mép trên
      // đọc như thể nó bắt đầu từ giữa câu.
      top: Math.max(0, dinh - khung.clientHeight * 0.3),
      left: Math.max(0, trai - khung.clientWidth * 0.15),
      behavior: "smooth",
    });
  }, [hop, trangHienTai, phongThat]);

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

      // "Vừa bề ngang" phải đo trang thật rồi mới quy ra tỉ lệ: khổ giấy khác
      // nhau giữa các tài liệu, và cả giữa các trang của cùng một tài liệu.
      let tiLe = phong ?? 1;
      if (phong === null && beNgang > 0) {
        const goc = page.getViewport({ scale: 1 });
        // Trừ phần đệm hai bên của khung cuộn.
        tiLe = Math.max(0.2, (beNgang - 24) / goc.width);
      }
      setPhongThat(tiLe);

      // Nhân với tỉ lệ điểm ảnh của màn hình rồi thu lại bằng CSS: không có
      // bước này thì chữ trên màn hình HiDPI nhoè hẳn.
      const dpr = window.devicePixelRatio || 1;
      const viewport = page.getViewport({ scale: tiLe });
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
  }, [trangHienTai, phong, beNgang]);

  useEffect(() => {
    void ve();
  }, [ve, tongTrang]);

  // Vẽ xong thì đưa đoạn được trích vào tầm mắt. Không có bước này thì bấm một
  // chip trỏ tới cuối trang sẽ mở ra một khoảng lề trắng.
  useEffect(() => {
    if (!dangVe && kichThuoc.cao > 0) veDoanTrich();
  }, [dangVe, kichThuoc.cao, veDoanTrich]);

  if (loi) return <p className="p-4 text-sm text-canh-bao">{loi}</p>;

  const hopTrangNay = hop.filter((h) => h.page === trangHienTai);
  const trangCoDoanTrich = hop.length > 0 ? hop[0].page : null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-vien px-3 py-2 text-xs">
        <button
          onClick={() => setTrangHienTai((n) => Math.max(1, n - 1))}
          disabled={trangHienTai <= 1}
          aria-label={t("xem.trangTruoc")}
          className="rounded border border-vien px-2 py-1 text-mo hover:border-nhan hover:text-nhan disabled:opacity-40 disabled:hover:border-vien disabled:hover:text-mo"
        >
          ‹
        </button>
        <span className="tabular-nums text-mo">
          {trangHienTai}/{tongTrang || "…"}
        </span>
        <button
          onClick={() => setTrangHienTai((n) => Math.min(tongTrang || n, n + 1))}
          disabled={!tongTrang || trangHienTai >= tongTrang}
          aria-label={t("xem.trangSau")}
          className="rounded border border-vien px-2 py-1 text-mo hover:border-nhan hover:text-nhan disabled:opacity-40 disabled:hover:border-vien disabled:hover:text-mo"
        >
          ›
        </button>

        {/* Đường về. Người dùng cuộn đi đọc phần xung quanh rồi muốn quay lại
            đúng chỗ được trích — không có nút này thì phải bấm lại chip. */}
        {trangCoDoanTrich !== null && (
          <button
            onClick={() => {
              if (trangHienTai !== trangCoDoanTrich) setTrangHienTai(trangCoDoanTrich);
              else veDoanTrich();
            }}
            className="ml-1 flex items-center gap-1 rounded border border-vien px-2 py-1 text-mo hover:border-nhan hover:text-nhan"
          >
            <Bt.ngam size={12} />
            {t("xem.veDoanTrich")}
          </button>
        )}

        <select
          value={phong === null ? "vua" : String(phong)}
          onChange={(e) =>
            setPhong(e.target.value === "vua" ? null : Number(e.target.value))
          }
          aria-label={t("xem.mucPhong")}
          className="ml-auto rounded border border-vien bg-the px-1.5 py-1 text-mo"
        >
          {MUC_PHONG.map((m) => (
            <option key={m ?? "vua"} value={m === null ? "vua" : m}>
              {m === null ? t("xem.vuaBeNgang") : `${Math.round(m * 100)}%`}
            </option>
          ))}
        </select>
      </div>

      <div ref={khungRef} className="min-h-0 flex-1 overflow-auto bg-nen p-3">
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
                left: h.x0 * phongThat,
                top: h.y0 * phongThat,
                width: (h.x1 - h.x0) * phongThat,
                height: (h.y1 - h.y0) * phongThat,
                background: "var(--to-sang)",
                boxShadow: "inset 0 0 0 1px var(--to-sang-vien)",
                mixBlendMode: "multiply",
              }}
            />
          ))}

          {dangVe && (
            <div className="absolute inset-0 grid place-items-center bg-nen/60 text-xs text-mo">
              {t("xem.dangDungTrang")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
