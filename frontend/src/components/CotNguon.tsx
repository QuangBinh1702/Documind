"use client";

/**
 * Cột nguồn — US-006, US-016 AC-4, US-038.
 *
 * Mỗi nguồn hiện tên, loại, số trang và **trạng thái xử lý**. Trạng thái là thứ
 * quan trọng nhất ở đây: tài liệu vừa tải lên chưa hỏi được ngay, và không nói
 * ra thì người dùng hỏi rồi tưởng hệ thống dốt.
 */

import { useRef, useState } from "react";
import { ApiError, type Nguon, api, taiLen } from "@/lib/api";

const BIEU_TUONG: Record<string, string> = {
  pdf: "PDF",
  docx: "DOC",
  txt: "TXT",
  md: "MD",
};

const NHAN_TRANG_THAI: Record<string, string> = {
  queued: "đang chờ",
  parsing: "đang đọc",
  ocr: "đang nhận dạng chữ",
  chunking: "đang chia đoạn",
  embedding: "đang lập chỉ mục",
  ready: "sẵn sàng",
  failed: "lỗi",
};

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

  async function tai(files: FileList | null) {
    if (!files?.length) return;
    setLoi(null);
    for (const f of Array.from(files)) {
      setDangTai({ ten: f.name, phanTram: 0 });
      try {
        await taiLen(nbId, f, (p) => setDangTai({ ten: f.name, phanTram: p }));
        onDoiThay();
      } catch (err) {
        setLoi(err instanceof ApiError ? err.message : `Không tải được ${f.name}.`);
      }
    }
    setDangTai(null);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-vien px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-mo">Nguồn</h2>
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
        <p className="text-sm">Kéo thả tệp vào đây</p>
        <p className="mt-1 text-xs text-mo">PDF · DOCX · TXT · MD, tối đa 50 MB</p>
        <button
          onClick={() => chonTep.current?.click()}
          className="mt-3 rounded-md border border-nhan px-3 py-1.5 text-sm text-nhan"
        >
          Chọn tệp
        </button>
        <input
          ref={chonTep}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md"
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
            Chưa có tài liệu nào. Tải một tệp lên để bắt đầu hỏi.
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
                  title="Hỏi trong tài liệu này"
                  className="mt-1 accent-nhan"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium" title={s.original_name}>
                    {s.title}
                  </p>
                  <p className="mt-0.5 text-xs text-mo">
                    {BIEU_TUONG[s.kind] ?? s.kind.toUpperCase()}
                    {s.page_count ? ` · ${s.page_count} trang` : ""} ·{" "}
                    <TrangThai nguon={s} />
                  </p>
                  {s.status === "failed" && s.error_message && (
                    <p className="mt-1 text-xs text-canh-bao">{s.error_message}</p>
                  )}
                </div>
                <button
                  onClick={async () => {
                    if (!confirm(`Xoá "${s.title}"?`)) return;
                    await api.xoaNguon(nbId, s.id);
                    onDoiThay();
                  }}
                  className="text-xs text-mo hover:text-canh-bao"
                  title="Xoá nguồn"
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

function TrangThai({ nguon }: { nguon: Nguon }) {
  const nhan = NHAN_TRANG_THAI[nguon.status] ?? nguon.status;
  if (nguon.status === "ready") return <span className="text-nhan">{nhan}</span>;
  if (nguon.status === "failed") return <span className="text-canh-bao">{nhan}</span>;
  return (
    <span className="text-mo">
      {nhan} {nguon.progress}%
    </span>
  );
}
