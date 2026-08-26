"use client";

/**
 * Cột hội thoại — US-012, US-013, US-014, US-018, US-032, US-033.
 *
 * Câu trả lời hiện dần theo từng mẩu, và marker `[n]` biến thành chip bấm được.
 * Marker mà không có trích dẫn tương ứng thì hiện mờ và không bấm được: mô hình
 * đôi khi bịa ra số đoạn không tồn tại, và một chip bấm vào không đi đâu cả làm
 * người dùng mất niềm tin vào toàn bộ tính năng trích dẫn.
 *
 * Lịch sử (US-018): mở notebook là thấy lại phiên gần nhất, chip vẫn bấm được;
 * chip của nguồn đã xoá hiện mờ. Nút "Hội thoại mới" bắt đầu một phiên khác —
 * máy chủ tạo phiên ở câu hỏi đầu tiên và báo lại qua sự kiện `session`.
 *
 * Hỏi ra ngoài (US-032): chỉ hiện nút sau khi cổng ngưỡng từ chối, và câu trả
 * lời ngoài được đóng khung khác hẳn câu trả lời có căn cứ (US-033).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type TinNhan, type TrichDan, api, taiVe } from "@/lib/api";
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
  reading: "buoc.reading",
  retrieving: "buoc.retrieving",
  reranking: "buoc.reranking",
  generating: "buoc.generating",
  verifying: "buoc.verifying",
  regenerating: "buoc.regenerating",
  calling_external: "buoc.calling_external",
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
  /** Marker của nguồn đã xoá — chip mờ, không bấm được. */
  markerChet: Set<number>;
  tuChoi: boolean;
  /** Câu trả lời từ dịch vụ ngoài, không dựa trên tài liệu (US-033). */
  ngoai: boolean;
  /** Lấy lại từ bộ nhớ đệm — hiện câu hỏi gốc để người dùng tự đối chiếu (US-034 AC-3). */
  tuCache: string | null;
  trangThai: string | null;
  xong: boolean;
  loi: string | null;
};

const LUOT_TRONG: Omit<Luot, "cauHoi"> = {
  traLoi: "",
  trichDan: {},
  markerChet: new Set(),
  tuChoi: false,
  ngoai: false,
  tuCache: null,
  trangThai: null,
  xong: false,
  loi: null,
};

/** Dựng lại các lượt từ tin nhắn đã lưu — mỗi cặp user/assistant là một lượt. */
function tuTinNhan(ds: TinNhan[]): Luot[] {
  const out: Luot[] = [];
  for (const m of ds) {
    if (m.role === "user") {
      out.push({ ...LUOT_TRONG, cauHoi: m.content, markerChet: new Set() });
      continue;
    }
    const l = out[out.length - 1];
    if (!l) continue;
    const trichDan: Record<number, TrichDan> = {};
    const chet = new Set<number>();
    for (const c of m.citations) {
      if (c.deleted || c.chunk_id === null) {
        chet.add(c.marker);
        continue;
      }
      trichDan[c.marker] = {
        marker: c.marker,
        chunk_id: c.chunk_id,
        source_id: "",
        page: c.page,
        char_start: 0,
        char_end: 0,
        snippet: c.snippet,
        heading_path: null,
      };
    }
    out[out.length - 1] = {
      ...l,
      traLoi: m.content,
      trichDan,
      markerChet: chet,
      tuChoi: m.answer_kind === "no_answer",
      ngoai: m.answer_kind === "external" || m.answer_kind === "cached_external",
      xong: true,
    };
  }
  return out;
}

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
  const [dangTaiLichSu, setDangTaiLichSu] = useState(true);
  // Máy chủ tạo phiên ở lượt hỏi đầu tiên và báo lại qua sự kiện `session`.
  // Không có id này thì không xuất được — nên giữ nó ngay khi nhận.
  const [phienId, setPhienId] = useState<string | null>(null);
  const [dangXuat, setDangXuat] = useState(false);
  const [thongBao, setThongBao] = useState<string | null>(null);
  const [hoiXacNhanNgoai, setHoiXacNhanNgoai] = useState<string | null>(null);
  const cuoiRef = useRef<HTMLDivElement>(null);
  const { t } = useNgonNgu();

  // ── Khôi phục phiên gần nhất — US-018 AC-3 ──────────
  useEffect(() => {
    let huy = false;
    setDangTaiLichSu(true);
    setLuot([]);
    setPhienId(null);
    (async () => {
      try {
        const phien = await api.danhSachPhien(nbId);
        if (huy || !phien.length) return;
        const moiNhat = phien[0];
        const tin = await api.tinNhanCuaPhien(moiNhat.id);
        if (huy) return;
        setPhienId(moiNhat.id);
        setLuot(tuTinNhan(tin));
      } catch {
        /* không có lịch sử thì bắt đầu trống — không phải lỗi đáng chặn */
      } finally {
        if (!huy) setDangTaiLichSu(false);
      }
    })();
    return () => {
      huy = true;
    };
  }, [nbId]);

  useEffect(() => {
    cuoiRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [luot]);

  const themLuot = useCallback((q: string): ((sua: (l: Luot) => Luot) => void) => {
    let chiSo = -1;
    setLuot((cu) => {
      chiSo = cu.length;
      return [...cu, { ...LUOT_TRONG, cauHoi: q, markerChet: new Set() }];
    });
    return (sua) => setLuot((cu) => cu.map((l, i) => (i === chiSo ? sua(l) : l)));
  }, []);

  /** Xử lý sự kiện chung cho cả hai đường hỏi. */
  function xuLy(capNhat: (sua: (l: Luot) => Luot) => void, e: SuKien): void {
    switch (e.type) {
      case "session":
        setPhienId(String(e.session_id));
        break;
      // `external_call` cố ý KHÔNG hiện gì trong khung chat. Việc dữ liệu đi
      // đâu là thuộc tính của cả không gian làm việc, không phải của từng câu
      // trả lời, nên nó nằm ở nhãn trên thanh tiêu đề.
      case "external_call":
      case "meta":
      case "condensed":
      case "context_trimmed":
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
      case "warning":
        capNhat((l) => ({ ...l, ngoai: true }));
        break;
      case "cache_hit":
        capNhat((l) => ({ ...l, ngoai: true, tuCache: String(e.cached_question) }));
        break;
      case "error":
        capNhat((l) => ({ ...l, loi: String(e.message), xong: true }));
        break;
      case "done":
        capNhat((l) => ({ ...l, xong: true, trangThai: null }));
        break;
    }
  }

  async function gui(e: React.FormEvent) {
    e.preventDefault();
    const q = cauHoi.trim();
    if (!q || dangHoi) return;

    setCauHoi("");
    setDangHoi(true);
    const capNhat = themLuot(q);
    await hoi({ question: q, notebook_id: nbId, session_id: phienId }, (ev) =>
      xuLy(capNhat, ev),
    );
    setDangHoi(false);
  }

  /**
   * Hỏi bằng kiến thức ngoài tài liệu — US-032.
   *
   * Ở Privacy Mode máy chủ trả `confirm_required` trước; giao diện hỏi lại
   * người dùng rồi gọi tiếp với `confirmed: true`. Câu trả lời hiện thành một
   * lượt riêng, đóng khung khác (US-033 AC-1).
   */
  async function hoiNgoai(q: string, confirmed = false) {
    if (dangHoi) return;
    setDangHoi(true);
    setHoiXacNhanNgoai(null);
    let canXacNhan = false;
    const capNhat = themLuot(q);
    await hoi(
      { question: q, notebook_id: nbId, session_id: phienId, confirmed },
      (ev) => {
        if (ev.type === "confirm_required") {
          canXacNhan = true;
          return;
        }
        xuLy(capNhat, ev);
      },
      "/api/chat/ask-external",
    );
    setDangHoi(false);
    if (canXacNhan) {
      // Bỏ lượt trống vừa thêm; hộp xác nhận sẽ gọi lại khi người dùng đồng ý.
      setLuot((cu) => cu.slice(0, -1));
      setHoiXacNhanNgoai(q);
    }
  }

  function hoiThoaiMoi() {
    if (dangHoi) return;
    setLuot([]);
    setPhienId(null);
    setThongBao(null);
  }

  async function xuat(dinhDang: "md" | "pdf") {
    if (!phienId || dangXuat) return;
    setDangXuat(true);
    setThongBao(null);
    try {
      await taiVe(
        `/api/sessions/${phienId}/export?dinh_dang=${dinhDang}`,
        `hoi-dap.${dinhDang}`,
      );
    } catch (err) {
      // Báo ở thanh riêng, không đè lên câu trả lời cuối — câu trả lời không
      // có lỗi gì, tệp xuất mới có.
      setThongBao(err instanceof ApiError ? err.message : t("chat.khongXuatDuoc"));
    } finally {
      setDangXuat(false);
    }
  }

  const coGiDeXuat = phienId !== null && luot.some((l) => l.xong && !l.loi);

  return (
    <div className="flex h-full flex-col">
      {(coGiDeXuat || luot.length > 0) && (
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-b border-vien px-6 py-2">
          <button
            onClick={hoiThoaiMoi}
            disabled={dangHoi}
            className="mr-auto rounded-md border border-vien px-2.5 py-1 text-xs text-mo hover:border-nhan hover:text-nhan disabled:opacity-45"
          >
            + {t("chat.hoiThoaiMoi")}
          </button>
          {/* Thanh xuất chỉ hiện khi đã có gì để xuất — US-040. */}
          {coGiDeXuat && (
            <>
              <span className="text-xs text-mo">{t("chat.luuLai")}</span>
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
            </>
          )}
        </div>
      )}

      {thongBao && (
        <div
          role="alert"
          className="flex shrink-0 items-center gap-3 border-b border-canh-bao bg-canh-bao-nen px-6 py-2 text-sm text-canh-bao"
        >
          <span className="flex-1">{thongBao}</span>
          <button onClick={() => setThongBao(null)} className="text-xs underline">
            {t("chung.dong")}
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        {luot.length === 0 && !dangTaiLichSu && (
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

              {/* Câu trả lời ngoài tài liệu được đánh dấu rõ — US-033 AC-1. */}
              {l.ngoai && (
                <p className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-canh-bao px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-canh-bao">
                  {t("chat.nhanNgoai")}
                </p>
              )}

              <div
                className={`mt-2 whitespace-pre-wrap rounded-xl border px-4 py-3.5 ${
                  l.loi
                    ? "border-canh-bao bg-canh-bao-nen"
                    : l.ngoai
                      ? "border-dashed border-canh-bao bg-canh-bao-nen/40"
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
                    markerChet={l.markerChet}
                    onChon={onChonTrichDan}
                  />
                ) : (
                  <span className="text-sm italic text-mo">
                    {l.trangThai ?? t("chung.dangXuLy")}…
                  </span>
                )}
              </div>

              {l.tuCache && (
                <p className="mt-2 text-xs text-mo">
                  {t("chat.tuCache", { cau: l.tuCache })}
                </p>
              )}

              {l.xong && !l.loi && Object.keys(l.trichDan).length > 0 && (
                <p className="mt-2 text-xs text-mo">
                  {t("chat.soTrichDan", { so: Object.keys(l.trichDan).length })}
                </p>
              )}

              {/* Mời hỏi ra ngoài — chỉ sau khi cổng ngưỡng đã từ chối (US-032 AC-1). */}
              {l.xong && l.tuChoi && !l.ngoai && i === luot.length - 1 && !dangHoi && (
                <button
                  onClick={() => void hoiNgoai(l.cauHoi)}
                  className="mt-2 rounded-md border border-canh-bao px-3 py-1.5 text-xs font-medium text-canh-bao hover:bg-canh-bao-nen"
                >
                  {t("chat.hoiNgoai")}
                </button>
              )}
            </div>
          ))}
          <div ref={cuoiRef} />
        </div>
      </div>

      {/* Xác nhận trước khi gửi câu hỏi ra ngoài ở Privacy Mode — US-032 AC-4. */}
      {hoiXacNhanNgoai && (
        <div className="shrink-0 border-t border-canh-bao bg-canh-bao-nen px-6 py-3">
          <div className="mx-auto flex max-w-[68ch] flex-wrap items-center gap-3">
            <p className="flex-1 text-sm text-canh-bao">{t("chat.xacNhanNgoai")}</p>
            <button
              onClick={() => void hoiNgoai(hoiXacNhanNgoai, true)}
              className="rounded-md bg-canh-bao px-3 py-1.5 text-xs font-medium text-nen"
            >
              {t("chat.dongYGui")}
            </button>
            <button
              onClick={() => setHoiXacNhanNgoai(null)}
              className="rounded-md border border-canh-bao px-3 py-1.5 text-xs text-canh-bao"
            >
              {t("chung.huy")}
            </button>
          </div>
        </div>
      )}

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
            className="rounded-md bg-nhan px-5 py-2 font-medium text-nen disabled:opacity-45"
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
  markerChet,
  onChon,
}: {
  text: string;
  trichDan: Record<number, TrichDan>;
  markerChet: Set<number>;
  onChon: (t: TrichDan) => void;
}) {
  const { t } = useNgonNgu();
  const phan = text.split(/(\[\d{1,3}\])/g);
  return (
    <>
      {phan.map((p, i) => {
        const khop = /^\[(\d{1,3})\]$/.exec(p);
        if (!khop) return <span key={i}>{p}</span>;

        const so = Number(khop[1]);
        const cite = trichDan[so];
        const daXoa = markerChet.has(so);
        return (
          <button
            key={i}
            type="button"
            disabled={!cite}
            onClick={() => cite && onChon(cite)}
            className={`chip${cite ? "" : " chip-chet"}`}
            title={cite ? t("chip.xemDoanGoc") : daXoa ? t("chip.nguonDaXoa") : t("chip.khongTonTai")}
          >
            {so}
          </button>
        );
      })}
    </>
  );
}
