"use client";

/**
 * Cột hội thoại — US-012, US-013, US-014, US-018, US-032, US-033.
 *
 * Câu trả lời hiện dần theo từng mẩu, dựng từ Markdown, và marker `[n]` biến
 * thành chip bấm được (`VanBanTraLoi`). Marker không có trích dẫn tương ứng
 * thì hiện mờ và không bấm được: mô hình đôi khi bịa ra số đoạn không tồn tại,
 * và một chip bấm vào không đi đâu cả làm người dùng mất niềm tin vào toàn bộ
 * tính năng trích dẫn.
 *
 * Lịch sử (US-018): mở notebook là thấy lại phiên gần nhất, đổi được sang phiên
 * cũ hơn, chip vẫn bấm được; chip của nguồn đã xoá hiện mờ. "Hội thoại mới"
 * bắt đầu một phiên khác — máy chủ tạo phiên ở câu hỏi đầu tiên và báo lại
 * qua sự kiện `session`.
 *
 * Hỏi ra ngoài (US-032): chỉ hiện nút sau khi cổng ngưỡng từ chối, và câu trả
 * lời ngoài được đóng khung khác hẳn câu trả lời có căn cứ (US-033).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  type PhienHoiThoai,
  type TinNhan,
  type TrichDan,
  api,
  taiVe,
} from "@/lib/api";
import { Bt } from "@/components/BieuTuong";
import { useNgonNgu } from "@/components/NgonNguProvider";
import { VanBanTraLoi } from "@/components/VanBanTraLoi";
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
  moHinh: string | null;
  doTreMs: number | null;
};

const LUOT_TRONG: Omit<Luot, "cauHoi" | "markerChet"> = {
  traLoi: "",
  trichDan: {},
  tuChoi: false,
  ngoai: false,
  tuCache: null,
  trangThai: null,
  xong: false,
  loi: null,
  moHinh: null,
  doTreMs: null,
};

function luotMoi(cauHoi: string): Luot {
  return { ...LUOT_TRONG, cauHoi, markerChet: new Set() };
}

/** Dựng lại các lượt từ tin nhắn đã lưu — mỗi cặp user/assistant là một lượt. */
function tuTinNhan(ds: TinNhan[]): Luot[] {
  const out: Luot[] = [];
  for (const m of ds) {
    if (m.role === "user") {
      out.push(luotMoi(m.content));
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
      moHinh: m.model_used,
      doTreMs: m.latency_ms,
    };
  }
  return out;
}

/** "local:qwen3:8b" → "qwen3:8b"; "ollama-cloud:gemma4:31b" → "gemma4:31b". */
function tenMoHinh(raw: string | null): string | null {
  if (!raw) return null;
  return raw.replace(/^(local|ollama-cloud|gemini):/, "");
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
  const [phienDs, setPhienDs] = useState<PhienHoiThoai[]>([]);
  // Máy chủ tạo phiên ở lượt hỏi đầu tiên và báo lại qua sự kiện `session`.
  // Không có id này thì không xuất được — nên giữ nó ngay khi nhận.
  const [phienId, setPhienId] = useState<string | null>(null);
  const [dangXuat, setDangXuat] = useState(false);
  const [thongBao, setThongBao] = useState<string | null>(null);
  const [hoiXacNhanNgoai, setHoiXacNhanNgoai] = useState<string | null>(null);
  const cuoiRef = useRef<HTMLDivElement>(null);
  const oNhapRef = useRef<HTMLTextAreaElement>(null);
  const { t } = useNgonNgu();

  const taiPhien = useCallback(async (id: string) => {
    const tin = await api.tinNhanCuaPhien(id);
    setPhienId(id);
    setLuot(tuTinNhan(tin));
  }, []);

  // ── Khôi phục phiên gần nhất — US-018 AC-3 ──────────
  useEffect(() => {
    let huy = false;
    setDangTaiLichSu(true);
    setLuot([]);
    setPhienId(null);
    (async () => {
      try {
        const phien = await api.danhSachPhien(nbId);
        if (huy) return;
        setPhienDs(phien);
        if (phien.length) await taiPhien(phien[0].id);
      } catch {
        /* không có lịch sử thì bắt đầu trống — không phải lỗi đáng chặn */
      } finally {
        if (!huy) setDangTaiLichSu(false);
      }
    })();
    return () => {
      huy = true;
    };
  }, [nbId, taiPhien]);

  useEffect(() => {
    cuoiRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [luot]);

  // Ô nhập tự cao theo nội dung, tối đa ~6 dòng.
  useEffect(() => {
    const o = oNhapRef.current;
    if (!o) return;
    o.style.height = "0px";
    o.style.height = `${Math.min(o.scrollHeight, 160)}px`;
  }, [cauHoi]);

  const themLuot = useCallback((q: string): ((sua: (l: Luot) => Luot) => void) => {
    let chiSo = -1;
    setLuot((cu) => {
      chiSo = cu.length;
      return [...cu, luotMoi(q)];
    });
    return (sua) => setLuot((cu) => cu.map((l, i) => (i === chiSo ? sua(l) : l)));
  }, []);

  /** Xử lý sự kiện chung cho cả hai đường hỏi. */
  function xuLy(capNhat: (sua: (l: Luot) => Luot) => void, e: SuKien): void {
    switch (e.type) {
      case "session":
        setPhienId(String(e.session_id));
        setPhienDs((cu) =>
          cu.some((p) => p.id === e.session_id)
            ? cu
            : [
                { id: String(e.session_id), title: String(e.title ?? ""), updated_at: "" },
                ...cu,
              ],
        );
        break;
      case "meta":
        capNhat((l) => ({ ...l, moHinh: String(e.model ?? "") || null }));
        break;
      // `external_call` cố ý KHÔNG hiện gì trong khung chat. Việc dữ liệu đi
      // đâu là thuộc tính của cả không gian làm việc, không phải của từng câu
      // trả lời, nên nó nằm ở nhãn trên thanh tiêu đề.
      case "external_call":
      case "condensed":
      case "context_trimmed":
      case "saved":
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
        capNhat((l) => ({
          ...l,
          xong: true,
          trangThai: null,
          doTreMs: typeof e.latency_ms === "number" ? e.latency_ms : l.doTreMs,
        }));
        break;
    }
  }

  async function gui() {
    const q = cauHoi.trim();
    if (!q || dangHoi) return;

    setCauHoi("");
    setDangHoi(true);
    const capNhat = themLuot(q);
    await hoi({ question: q, notebook_id: nbId, session_id: phienId }, (ev) =>
      xuLy(capNhat, ev),
    );
    setDangHoi(false);
    oNhapRef.current?.focus();
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
    oNhapRef.current?.focus();
  }

  async function doiPhien(id: string) {
    if (dangHoi || id === phienId) return;
    try {
      await taiPhien(id);
    } catch {
      setThongBao(t("nb.khongTaiDuoc"));
    }
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
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-vien px-5 py-2">
        <button
          onClick={hoiThoaiMoi}
          disabled={dangHoi}
          className="nut-phu"
          title={t("chat.hoiThoaiMoi")}
        >
          <Bt.them size={14} /> {t("chat.hoiThoaiMoi")}
        </button>

        {phienDs.length > 0 && (
          <select
            value={phienId ?? ""}
            onChange={(e) => e.target.value && void doiPhien(e.target.value)}
            disabled={dangHoi}
            aria-label={t("chat.chonPhien")}
            className="max-w-[16rem] truncate rounded-md border border-vien bg-the px-2 py-1 text-xs text-mo outline-none focus:border-nhan"
          >
            {phienId === null && <option value="">{t("chat.phienMoi")}</option>}
            {phienDs.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title || t("chat.phienKhongTen")}
              </option>
            ))}
          </select>
        )}

        {/* Xuất — một nút, hai lựa chọn; chỉ hiện khi đã có gì để xuất (US-040). */}
        {coGiDeXuat && (
          <MenuXuat dangXuat={dangXuat} onXuat={(d) => void xuat(d)} />
        )}
      </div>

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

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-8">
        {luot.length === 0 && !dangTaiLichSu && (
          <div className="mx-auto max-w-[68ch] rounded-2xl border border-dashed border-vien px-6 py-12 text-center">
            <BieuTuongHoi />
            <p className="mt-4 text-[15px] font-semibold tracking-tight">
              {sanSang ? t("chat.batDau") : t("chat.chuaCoTaiLieu")}
            </p>
            <p className="mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-mo">
              {sanSang ? t("chat.batDauMoTa") : t("chat.canXuLyXong")}
            </p>
            {/* US-042 AC-1 — lời gọi hành động, không chỉ mô tả tình trạng. */}
            {!sanSang && (
              <button onClick={onTaiTaiLieu} className="nut-chinh mt-5">
                {t("chat.taiLenDauTien")}
              </button>
            )}
          </div>
        )}

        <div className="mx-auto max-w-[68ch] space-y-8">
          {luot.map((l, i) => (
            <LuotHoiDap
              key={i}
              l={l}
              cuoi={i === luot.length - 1}
              dangHoi={dangHoi}
              onChonTrichDan={onChonTrichDan}
              onHoiNgoai={() => void hoiNgoai(l.cauHoi)}
            />
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

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void gui();
        }}
        className="shrink-0 border-t border-vien px-5 py-4 sm:px-8"
      >
        <div className="o-nhap mx-auto flex max-w-[68ch] items-end gap-2">
          <textarea
            ref={oNhapRef}
            rows={1}
            value={cauHoi}
            onChange={(e) => setCauHoi(e.target.value)}
            onKeyDown={(e) => {
              // Enter gửi; Shift+Enter xuống dòng — quy ước quen thuộc của mọi
              // khung chat, và câu hỏi hiếm khi cần nhiều dòng.
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void gui();
              }
            }}
            disabled={dangHoi}
            placeholder={sanSang ? t("chat.oNhap") : t("chat.chuaSanSang")}
            className="max-h-40 min-h-[42px] flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] leading-relaxed outline-none placeholder:text-mo/70 disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={!cauHoi.trim() || dangHoi}
            className="nut-chinh mb-1 mr-1"
            aria-label={t("chat.hoi")}
          >
            {dangHoi ? <span className="dang-cho" aria-hidden="true" /> : <Bt.gui size={16} />}
          </button>
        </div>
        <p className="mx-auto mt-1.5 max-w-[68ch] text-[11px] text-mo/70">
          {t("chat.goiYPhim")}
        </p>
      </form>
    </div>
  );
}

function MenuXuat({
  dangXuat,
  onXuat,
}: {
  dangXuat: boolean;
  onXuat: (d: "md" | "pdf") => void;
}) {
  const [mo, setMo] = useState(false);
  const { t } = useNgonNgu();
  return (
    <div className="relative ml-auto">
      <button
        onClick={() => setMo((m) => !m)}
        disabled={dangXuat}
        aria-expanded={mo}
        aria-haspopup="menu"
        className="nut-phu h-8 gap-1.5"
        title={t("chat.luuLai")}
      >
        {dangXuat ? <span className="dang-cho" /> : <Bt.xuat size={14} />}
        {t("chat.xuat")}
        <Bt.mui size={12} />
      </button>
      {mo && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setMo(false)} />
          <div role="menu" className="menu-noi absolute right-0 z-30 mt-2 w-44 py-1.5">
            {(["md", "pdf"] as const).map((d) => (
              <button
                key={d}
                role="menuitem"
                className="muc-menu w-full"
                onClick={() => {
                  setMo(false);
                  onXuat(d);
                }}
              >
                <Bt.tep /> {d === "md" ? "Markdown" : "PDF"}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function LuotHoiDap({
  l,
  cuoi,
  dangHoi,
  onChonTrichDan,
  onHoiNgoai,
}: {
  l: Luot;
  cuoi: boolean;
  dangHoi: boolean;
  onChonTrichDan: (t: TrichDan) => void;
  onHoiNgoai: () => void;
}) {
  const { t } = useNgonNgu();
  const [daChep, setDaChep] = useState(false);
  const soTrichDan = Object.keys(l.trichDan).length;

  async function chep() {
    try {
      await navigator.clipboard.writeText(l.traLoi.replace(/\[\d{1,3}\]/g, "").trim());
      setDaChep(true);
      setTimeout(() => setDaChep(false), 1500);
    } catch {
      /* trình duyệt chặn clipboard */
    }
  }

  return (
    <div>
      <div className="flex justify-end">
        <p className="bong-bong-hoi">{l.cauHoi}</p>
      </div>

      {/* Câu trả lời ngoài tài liệu được đánh dấu rõ — US-033 AC-1. */}
      {l.ngoai && (
        <p className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-canh-bao px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-canh-bao">
          {t("chat.nhanNgoai")}
        </p>
      )}

      <div
        className={`mt-3 rounded-2xl border px-5 py-4 ${
          l.loi
            ? "border-canh-bao bg-canh-bao-nen"
            : l.ngoai
              ? "border-dashed border-canh-bao bg-canh-bao-nen/40"
              : l.tuChoi
                ? "border-dashed border-vien text-mo"
                : "border-vien bg-the shadow-[0_1px_0_rgba(0,0,0,0.03)]"
        }`}
      >
        {l.loi ? (
          <p className="text-sm">{l.loi}</p>
        ) : l.traLoi ? (
          <>
            <VanBanTraLoi
              text={l.traLoi}
              trichDan={l.trichDan}
              markerChet={l.markerChet}
              onChon={onChonTrichDan}
            />
            {!l.xong && <span className="con-tro-go" aria-hidden="true" />}
          </>
        ) : (
          <span className="inline-flex items-center gap-2 text-sm italic text-mo">
            <span className="dang-cho" aria-hidden="true" />
            {l.trangThai ?? t("chung.dangXuLy")}…
          </span>
        )}
      </div>

      {l.tuCache && (
        <p className="mt-2 text-xs text-mo">{t("chat.tuCache", { cau: l.tuCache })}</p>
      )}

      {l.xong && !l.loi && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-mo">
          {soTrichDan > 0 && <span>{t("chat.soTrichDan", { so: soTrichDan })}</span>}
          {tenMoHinh(l.moHinh) && <span className="tabular-nums">{tenMoHinh(l.moHinh)}</span>}
          {l.doTreMs !== null && (
            <span className="tabular-nums">{(l.doTreMs / 1000).toFixed(1)} s</span>
          )}
          {l.traLoi && !l.tuChoi && (
            <button onClick={() => void chep()} className="ml-auto inline-flex items-center gap-1 hover:text-chu">
              {daChep ? <Bt.kiem size={12} /> : <Bt.chep size={12} />}
              {daChep ? t("chat.daChep") : t("chat.chep")}
            </button>
          )}
        </div>
      )}

      {/* Mời hỏi ra ngoài — chỉ sau khi cổng ngưỡng đã từ chối (US-032 AC-1). */}
      {l.xong && l.tuChoi && !l.ngoai && cuoi && !dangHoi && (
        <button
          onClick={onHoiNgoai}
          className="mt-2 rounded-md border border-canh-bao px-3 py-1.5 text-xs font-medium text-canh-bao hover:bg-canh-bao-nen"
        >
          {t("chat.hoiNgoai")}
        </button>
      )}
    </div>
  );
}

function BieuTuongHoi() {
  return (
    <svg
      viewBox="0 0 64 48"
      className="mx-auto h-12 w-auto text-nhan"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinejoin="round"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M6 8a4 4 0 0 1 4-4h30a4 4 0 0 1 4 4v18a4 4 0 0 1-4 4H20l-8 7v-7h-2a4 4 0 0 1-4-4z" />
      <path d="M14 13h22M14 20h14" opacity={0.6} />
      <circle cx="50" cy="34" r="9" fill="currentColor" stroke="none" opacity={0.15} />
      <text x="50" y="38" textAnchor="middle" fontSize="11" fontWeight="700" fill="currentColor">
        1
      </text>
    </svg>
  );
}
