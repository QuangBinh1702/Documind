"use client";

/**
 * Cột nguồn — US-006, US-016 AC-4, US-038.
 *
 * Mỗi nguồn hiện tên, loại, số trang và **trạng thái xử lý**. Trạng thái là thứ
 * quan trọng nhất ở đây: tài liệu vừa tải lên chưa hỏi được ngay, và không nói
 * ra thì người dùng hỏi rồi tưởng hệ thống dốt.
 */

import { useEffect, useRef, useState } from "react";
import { ApiError, type Nguon, api, taiLen } from "@/lib/api";
import { useNgonNgu } from "@/components/NgonNguProvider";
import type { Khoa } from "@/lib/i18n";

const BIEU_TUONG: Record<string, string> = {
  pdf: "PDF",
  docx: "DOC",
  txt: "TXT",
  md: "MD",
  image: "IMG",
};

const DUOI_NHAN = ".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp";

/**
 * Nhãn trạng thái, dịch theo ngôn ngữ đang chọn — US-022 AC-2, US-036 AC-3.
 *
 * Khoá là **từ vựng của lược đồ** (`sources.status`), không phải chuỗi hiển
 * thị. Trạng thái nào chưa có nhãn thì hiện nguyên mã trạng thái — xấu, nhưng
 * đúng, và nó lộ ra ngay để bổ sung.
 */
const NHAN_TRANG_THAI = (t: Dich): Record<string, string> => ({
  queued: t("trangThai.queued"),
  parsing: t("trangThai.parsing"),
  ocr: t("trangThai.ocr"),
  chunking: t("trangThai.chunking"),
  embedding: t("trangThai.embedding"),
  ready: t("trangThai.ready"),
  failed: t("trangThai.failed"),
});

type Dich = (khoa: Khoa, tham?: Record<string, string | number>) => string;

export function CotNguon({
  nbId,
  nguon,
  onDoiThay,
}: {
  nbId: string;
  nguon: Nguon[];
  onDoiThay: () => void;
}) {
  const [dangTai, setDangTai] = useState<{ ten: string; phanTram: number } | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [keoVao, setKeoVao] = useState(false);
  const chonTep = useRef<HTMLInputElement>(null);
  const { t, soTrang } = useNgonNgu();

  async function tai(files: Iterable<File> | FileList | null) {
    const ds = files ? Array.from(files) : [];
    if (!ds.length) return;
    setLoi(null);
    for (const f of ds) {
      setDangTai({ ten: f.name, phanTram: 0 });
      try {
        await taiLen(nbId, f, (p) => setDangTai({ ten: f.name, phanTram: p }));
        onDoiThay();
      } catch (err) {
        setLoi(
          err instanceof ApiError
            ? err.message
            : t("nguon.khongTaiDuoc", { ten: f.name }),
        );
      }
    }
    setDangTai(null);
  }

  /**
   * Dán ảnh từ clipboard — US-025 AC-3.
   *
   * Ảnh chụp màn hình không có tên tệp: `getAsFile()` trả về một `File` tên
   * "image.png" hoặc rỗng. Đặt tên theo thời điểm dán để danh sách nguồn còn
   * phân biệt được nhiều ảnh dán liên tiếp với nhau.
   *
   * Nghe ở `window` chứ không ở một ô nhập: người dùng vừa chụp màn hình xong
   * thì con trỏ đang ở đâu là chuyện ngẫu nhiên. Nhưng bỏ qua khi họ đang gõ,
   * vì dán chữ vào ô câu hỏi là việc khác hẳn.
   */
  useEffect(() => {
    function danh(e: ClipboardEvent) {
      const dich = e.target as HTMLElement | null;
      if (dich?.closest("input, textarea, [contenteditable='true']")) return;

      const anh = Array.from(e.clipboardData?.items ?? [])
        .filter((it) => it.kind === "file" && it.type.startsWith("image/"))
        .map((it) => it.getAsFile())
        .filter((f): f is File => f !== null)
        .map((f, i) => {
          const duoi = f.type.split("/")[1]?.replace("jpeg", "jpg") ?? "png";
          const dau = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
          return new File([f], `anh-dan-${dau}${i ? `-${i + 1}` : ""}.${duoi}`, {
            type: f.type,
          });
        });

      if (anh.length) {
        e.preventDefault();
        void tai(anh);
      }
    }

    window.addEventListener("paste", danh);
    return () => window.removeEventListener("paste", danh);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nbId]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-vien px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-mo">
          {t("nguon.tieuDe")}
        </h2>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setKeoVao(true);
        }}
        onDragLeave={() => setKeoVao(false)}
        onDrop={(e) => {
          e.preventDefault();
          setKeoVao(false);
          void tai(e.dataTransfer.files);
        }}
        className={`m-3 rounded-lg border border-dashed px-4 py-5 text-center transition-colors ${
          keoVao ? "border-nhan bg-nhan/5" : "border-vien"
        }`}
      >
        <p className="text-sm">{t("nguon.keoTha")}</p>
        <p className="mt-1 text-xs text-mo">{t("nguon.dinhDang")}</p>
        <p className="mt-0.5 text-xs text-mo">{t("nguon.danAnh")}</p>
        <button
          onClick={() => chonTep.current?.click()}
          className="mt-3 rounded-md border border-nhan px-3 py-1.5 text-sm text-nhan"
        >
          {t("nguon.chonTep")}
        </button>
        <input
          ref={chonTep}
          type="file"
          multiple
          accept={DUOI_NHAN}
          className="hidden"
          onChange={(e) => {
            void tai(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {dangTai && (
        <div className="mx-3 mb-3">
          <p className="truncate text-xs text-mo">
            {dangTai.ten} — {dangTai.phanTram}%
          </p>
          {/* US-006 AC-6: thanh tiến trình theo phần trăm, không phải vòng xoay. */}
          <div className="mt-1 h-1 overflow-hidden rounded bg-vien">
            <div
              className="h-full bg-nhan transition-[width]"
              style={{ width: `${dangTai.phanTram}%` }}
            />
          </div>
        </div>
      )}

      {loi && <p className="mx-3 mb-3 text-xs text-canh-bao">{loi}</p>}

      <ul className="min-h-0 flex-1 overflow-y-auto">
        {nguon.length === 0 ? (
          <li className="px-4 py-3 text-sm text-mo">
            {t("nguon.chuaCo")}
          </li>
        ) : (
          nguon.map((s) => (
            <li key={s.id} className="border-b border-vien px-4 py-3">
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={s.in_scope}
                  disabled={s.status !== "ready"}
                  onChange={async () => {
                    await api.doiPhamVi(nbId, s.id, !s.in_scope);
                    onDoiThay();
                  }}
                  title={t("nguon.hoiTrong")}
                  className="mt-1 accent-nhan"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium" title={s.original_name}>
                    {s.title}
                  </p>
                  <p className="mt-0.5 text-xs text-mo">
                    {BIEU_TUONG[s.kind] ?? s.kind.toUpperCase()}
                    {/* Ảnh luôn là "1 trang" — một con số không nói gì thêm. */}
                    {s.kind !== "image" && s.page_count
                      ? ` · ${soTrang(s.page_count)}`
                      : ""}{" "}
                    ·{" "}
                    <TrangThai nguon={s} t={t} />
                  </p>
                  {s.status === "failed" && s.error_message && (
                    <p className="mt-1 text-xs text-canh-bao">{s.error_message}</p>
                  )}
                </div>
                <button
                  onClick={async () => {
                    if (!confirm(t("nguon.xoaHoi", { ten: s.title }))) return;
                    await api.xoaNguon(nbId, s.id);
                    onDoiThay();
                  }}
                  className="text-xs text-mo hover:text-canh-bao"
                  title={t("chung.xoa")}
                >
                  ✕
                </button>
              </div>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

function TrangThai({
  nguon,
  t,
}: {
  nguon: Nguon;
  t: Dich;
}) {
  const nhan = NHAN_TRANG_THAI(t)[nguon.status] ?? nguon.status;
  if (nguon.status === "ready") return <span className="text-nhan">{nhan}</span>;
  if (nguon.status === "failed") return <span className="text-canh-bao">{nhan}</span>;

  // `message` do luồng SSE gửi kèm và nói cụ thể hơn hẳn nhãn trạng thái —
  // "đang nhận dạng chữ 45/120 trang" thay vì "đang nhận dạng chữ" (US-022
  // AC-3). Không có luồng thì rơi về nhãn tĩnh.
  return (
    <span className="text-mo">
      {nguon.message ? nguon.message.replace(/…$/, "") : nhan} {nguon.progress}%
    </span>
  );
}
