"use client";

/**
 * Cột hội thoại — US-012, US-013, US-014.
 *
 * Câu trả lời hiện dần theo từng mẩu, và marker `[n]` biến thành chip bấm được.
 * Marker mà không có trích dẫn tương ứng thì hiện mờ và không bấm được: mô hình
 * đôi khi bịa ra số đoạn không tồn tại, và một chip bấm vào không đi đâu cả làm
 * người dùng mất niềm tin vào toàn bộ tính năng trích dẫn.
 */

import { useEffect, useRef, useState } from "react";
import { type TrichDan, taiVe } from "@/lib/api";
import { useNgonNgu } from "@/components/NgonNguProvider";
import type { Khoa } from "@/lib/i18n";
import { hoi, type SuKien } from "@/lib/stream";

/**
 * Nhãn cho từng bước xử lý — khoá là `stage` trong sự kiện SSE.
 *
 * Bước lạ trả về `null` thay vì hiện mã bước: `stage` là từ vựng của máy chủ,
 * và một chuỗi như `reranking` giữa cuộc hội thoại không nói gì với người dùng.
 * Giao diện rơi về "đang xử lý".
 */
const KHOA_BUOC: Record<string, Khoa> = {
  retrieving: "buoc.retrieving",
  reranking: "buoc.reranking",
  generating: "buoc.generating",
  verifying: "buoc.verifying",
  regenerating: "buoc.regenerating",
};

function nhanBuoc(
  t: (khoa: Khoa, tham?: Record<string, string | number>) => string,
  stage: string,
): string | null {
  return stage in KHOA_BUOC ? t(KHOA_BUOC[stage]) : null;
}

type Luot = {
  cauHoi: string;
  traLoi: string;
  trichDan: Record<number, TrichDan>;
  tuChoi: boolean;
  trangThai: string | null;
  xong: boolean;
  loi: string | null;
};

export function CotHoiDap({
  nbId,
  sanSang,
  onChonTrichDan,
  onTaiTaiLieu,
}: {
  nbId: string;
  sanSang: boolean;
  onChonTrichDan: (t: TrichDan) => void;
  /** Đưa người dùng tới chỗ tải tệp — trên màn hình hẹp cột nguồn đang bị ẩn. */
  onTaiTaiLieu: () => void;
}) {
  const [luot, setLuot] = useState<Luot[]>([]);
  const [cauHoi, setCauHoi] = useState("");
  const [dangHoi, setDangHoi] = useState(false);
  // Máy chủ tạo phiên ở lượt hỏi đầu tiên và báo lại qua sự kiện `session`.
  // Không có id này thì không xuất được — nên giữ nó ngay khi nhận.
  const [phienId, setPhienId] = useState<string | null>(null);
  const [dangXuat, setDangXuat] = useState(false);
  const cuoiRef = useRef<HTMLDivElement>(null);
  const { t } = useNgonNgu();

  useEffect(() => {
    cuoiRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [luot]);

  async function gui(e: React.FormEvent) {
    e.preventDefault();
    const q = cauHoi.trim();
    if (!q || dangHoi) return;

    setCauHoi("");
    setDangHoi(true);
    const chiSo = luot.length;
    setLuot((cu) => [
      ...cu,
      {
        cauHoi: q,
        traLoi: "",
        trichDan: {},
        tuChoi: false,
        trangThai: null,
        xong: false,
        loi: null,
      },
    ]);

    const capNhat = (sua: (l: Luot) => Luot) =>
      setLuot((cu) => cu.map((l, i) => (i === chiSo ? sua(l) : l)));

    await hoi({ question: q, notebook_id: nbId, session_id: phienId }, (e: SuKien) => {
      switch (e.type) {
        case "session":
          setPhienId(String(e.session_id));
          break;
        // `external_call` cố ý KHÔNG hiện gì trong khung chat. Việc dữ liệu đi
        // đâu là thuộc tính của cả không gian làm việc, không phải của từng câu
        // trả lời, nên nó nằm ở nhãn trên thanh tiêu đề. Nhét vào giữa cuộc hội
        // thoại thì mỗi lượt hỏi lại chen một câu về hạ tầng mà người dùng
        // không làm gì được.
        case "external_call":
          break;
        case "status":
          capNhat((l) => ({ ...l, trangThai: nhanBuoc(t, String(e.stage)) }));
          break;
        case "token":
          capNhat((l) => ({ ...l, traLoi: l.traLoi + String(e.text) }));
          break;
        case "replace":
          // Bản sinh lại thay thế toàn bộ; giao diện không rút lại được thứ đã
          // hiện nên phải vẽ lại từ đầu.
          capNhat((l) => ({ ...l, traLoi: String(e.text) }));
          break;
        case "citation":
          capNhat((l) => ({
            ...l,
            trichDan: { ...l.trichDan, [Number(e.marker)]: e as unknown as TrichDan },
          }));
          break;
        case "no_answer":
          capNhat((l) => ({ ...l, tuChoi: true }));
          break;
        case "error":
          capNhat((l) => ({ ...l, loi: String(e.message), xong: true }));
          break;
        case "done":
          capNhat((l) => ({ ...l, xong: true, trangThai: null }));
          break;
      }
    });

    setDangHoi(false);
  }

  async function xuat(dinhDang: "md" | "pdf") {
    if (!phienId || dangXuat) return;
    setDangXuat(true);
    try {
      await taiVe(
        `/api/sessions/${phienId}/export?dinh_dang=${dinhDang}`,
        `hoi-dap.${dinhDang}`,
      );
    } catch {
      setLuot((cu) =>
        cu.map((l, i) =>
          i === cu.length - 1 ? { ...l, loi: t("chat.khongXuatDuoc") } : l,
        ),
      );
    } finally {
      setDangXuat(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Thanh xuất chỉ hiện khi đã có gì để xuất — US-040. */}
      {phienId && luot.some((l) => l.xong) && (
        <div className="flex shrink-0 items-center justify-end gap-2 border-b border-vien px-6 py-2">
          <span className="mr-auto text-xs text-mo">{t("chat.luuLai")}</span>
          <button
            onClick={() => void xuat("md")}
            disabled={dangXuat}
            className="rounded-md border border-vien px-2.5 py-1 text-xs text-mo hover:border-nhan hover:text-nhan disabled:opacity-45"
          >
            Markdown
          </button>
          <button
            onClick={() => void xuat("pdf")}
            disabled={dangXuat}
            className="rounded-md border border-vien px-2.5 py-1 text-xs text-mo hover:border-nhan hover:text-nhan disabled:opacity-45"
          >
            PDF
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        {luot.length === 0 && (
          <div className="mx-auto max-w-[68ch] rounded-lg border border-dashed border-vien px-5 py-10 text-center">
            <p className="font-medium">
              {sanSang ? t("chat.batDau") : t("chat.chuaCoTaiLieu")}
            </p>
            <p className="mt-1 text-sm text-mo">
              {sanSang ? t("chat.batDauMoTa") : t("chat.canXuLyXong")}
            </p>
            {/* US-042 AC-1 — lời gọi hành động, không chỉ mô tả tình trạng. */}
            {!sanSang && (
              <button
                onClick={onTaiTaiLieu}
                className="mt-4 rounded-md bg-nhan px-4 py-2 text-sm font-medium text-nen"
              >
                {t("chat.taiLenDauTien")}
              </button>
            )}
          </div>
        )}

        <div className="mx-auto max-w-[68ch] space-y-7">
          {luot.map((l, i) => (
            <div key={i}>
              <p className="text-sm text-mo">
                <b className="font-semibold text-chu">{t("chat.ban")}</b> {l.cauHoi}
              </p>

              <div
                className={`mt-2 whitespace-pre-wrap rounded-xl border px-4 py-3.5 ${
                  l.loi
                    ? "border-canh-bao bg-canh-bao-nen"
                    : l.tuChoi
                      ? "border-dashed border-vien text-mo"
                      : "border-vien bg-the"
                }`}
              >
                {l.loi ? (
                  l.loi
                ) : l.traLoi ? (
                  <VanBanCoChip
                    text={l.traLoi}
                    trichDan={l.trichDan}
                    onChon={onChonTrichDan}
                  />
                ) : (
                  <span className="text-sm italic text-mo">
                    {l.trangThai ?? t("chung.dangXuLy")}…
                  </span>
                )}
              </div>

              {l.xong && !l.loi && l.trangThai === null && Object.keys(l.trichDan).length > 0 && (
                <p className="mt-2 text-xs text-mo">
                  {t("chat.soTrichDan", { so: Object.keys(l.trichDan).length })}
                </p>
              )}
            </div>
          ))}
          <div ref={cuoiRef} />
        </div>
      </div>

      <form onSubmit={gui} className="shrink-0 border-t border-vien px-6 py-4">
        <div className="mx-auto flex max-w-[68ch] gap-2">
          <input
            value={cauHoi}
            onChange={(e) => setCauHoi(e.target.value)}
            disabled={dangHoi}
            placeholder={sanSang ? t("chat.oNhap") : t("chat.chuaSanSang")}
            className="flex-1 rounded-md border border-vien bg-the px-3 py-2 outline-none focus:border-nhan disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={!cauHoi.trim() || dangHoi}
            className="rounded-md bg-nhan px-5 py-2 font-medium text-white disabled:opacity-45"
          >
            {dangHoi ? "…" : t("chat.hoi")}
          </button>
        </div>
      </form>
    </div>
  );
}

/** Biến `[n]` thành chip bấm được — US-014 AC-2. */
function VanBanCoChip({
  text,
  trichDan,
  onChon,
}: {
  text: string;
  trichDan: Record<number, TrichDan>;
  onChon: (t: TrichDan) => void;
}) {
  const { t } = useNgonNgu();
  const phan = text.split(/(\[\d{1,2}\])/g);
  return (
    <>
      {phan.map((p, i) => {
        const khop = /^\[(\d{1,2})\]$/.exec(p);
        if (!khop) return <span key={i}>{p}</span>;

        const so = Number(khop[1]);
        const cite = trichDan[so];
        return (
          <button
            key={i}
            type="button"
            disabled={!cite}
            onClick={() => cite && onChon(cite)}
            className={`chip${cite ? "" : " chip-chet"}`}
            title={cite ? t("chip.xemDoanGoc") : t("chip.khongTonTai")}
          >
            {so}
          </button>
        );
      })}
    </>
  );
}
