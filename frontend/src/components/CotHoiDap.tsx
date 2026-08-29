"use client";

/**
 * Cột hội thoại — US-012, US-013, US-014, US-018, US-025, US-032, US-033.
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
 * Hỏi ra ngoài (US-032): câu trả lời ngoài được đóng khung khác hẳn câu trả lời
 * có căn cứ (US-033). Hai đường đi tới đó, cả hai đều bắt đầu bằng một cú bấm:
 * nút dưới câu trả lời bị từ chối, hoặc công tắc "tự động hỏi ra ngoài" của cả
 * hội thoại. Công tắc mặc định tắt và **không** được nhớ qua lần mở trang sau —
 * xem `tuDongNgoai` bên dưới.
 *
 * Ô soạn câu hỏi mang bốn tiện ích nhỏ nhưng dùng liên tục: dừng giữa chừng,
 * phím ↑ lấy lại câu đã hỏi, Ctrl+V dán ảnh để hỏi ngay trên ảnh đó, và Enter
 * để gửi.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  type Nguon,
  type PhienHoiThoai,
  type TinNhan,
  type TrichDan,
  api,
  taiLen,
  taiVe,
} from "@/lib/api";
import { Bt } from "@/components/BieuTuong";
import { useNgonNgu } from "@/components/NgonNguProvider";
import { VanBanTraLoi } from "@/components/VanBanTraLoi";
import { anhTuClipboard } from "@/lib/anhDan";
import type { Khoa } from "@/lib/i18n";
import { hoi, type SuKien } from "@/lib/stream";
import { useTuyChon } from "@/lib/tuyChon";

/** Bề rộng cột đọc. Danh sách tin nhắn và ô soạn dùng CHUNG con số này —
 *  lệch nhau một chút là ô nhập trông như bị lệch khỏi cuộc hội thoại. */
const RONG_DOC = "mx-auto w-full max-w-[52rem]";

/** Số câu hỏi giữ lại cho phím ↑. Đủ cho một buổi làm việc, không phình. */
const LICH_SU_NHAP_TOI_DA = 60;

/** Chờ ảnh vừa dán chạy xong pipeline. OCR một ảnh chụp màn hình thường dưới
 *  mười giây; hai phút là giới hạn để không treo mãi khi worker chết. */
const CHO_ANH_MS = 120_000;

/** Trạng thái nguồn không đổi nữa. Mọi trạng thái khác là đang chạy dở. */
const TRANG_THAI_CUOI = new Set(["ready", "failed"]);

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

type Dich = (khoa: Khoa, tham?: Record<string, string | number>) => string;

function nhanBuoc(t: Dich, stage: string): string | null {
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
  /** Người dùng bấm dừng giữa chừng — câu trả lời còn dở. */
  daDung: boolean;
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
  daDung: false,
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

type DinhKem = { id: string; file: File; url: string };

/**
 * Lượt `i` có phải là một lượt từ chối đã được lượt sau trả lời hộ không?
 *
 * Nhận ra bằng hình dạng của dữ liệu — cùng câu hỏi, từ chối rồi trả lời ngoài
 * — chứ không bằng một cờ dựng lúc chạy. Nhờ vậy nó vẫn đúng sau khi tải lại
 * trang, lúc lịch sử được dựng lại từ tin nhắn đã lưu.
 */
function biNoiTiep(ds: Luot[], i: number): boolean {
  const l = ds[i];
  const sau = ds[i + 1];
  return Boolean(
    l && sau && l.tuChoi && !l.ngoai && sau.ngoai && sau.cauHoi === l.cauHoi,
  );
}

/** Kết cục của một lượt gọi — đủ để chỗ gọi quyết định có nối tiếp hay không. */
type KetCuc = { tuChoi: boolean; huy: boolean; canXacNhan: boolean };

export function CotHoiDap({
  nbId,
  nguon,
  sanSang,
  onChonTrichDan,
  onTaiTaiLieu,
  onThemNguon,
  onDoiPhien,
}: {
  nbId: string;
  /** Danh sách nguồn hiện tại — dùng để biết ảnh vừa dán đã xử lý xong chưa. */
  nguon: Nguon[];
  sanSang: boolean;
  onChonTrichDan: (t: TrichDan) => void;
  /** Đưa người dùng tới chỗ tải tệp — trên màn hình hẹp cột nguồn đang bị ẩn. */
  onTaiTaiLieu: () => void;
  /** Báo cho trang cha nạp lại danh sách nguồn và mở lại luồng theo dõi. */
  onThemNguon: () => void;
  /** Phiên đang mở đã đổi. Nút Chia sẻ trên thanh tiêu đề cần biết để chia sẻ
   *  đúng đoạn hội thoại người dùng đang nhìn — xem quyết định 0004. */
  onDoiPhien?: (id: string | null) => void;
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
  const [dinhKem, setDinhKem] = useState<DinhKem[]>([]);
  const [trangThaiAnh, setTrangThaiAnh] = useState<string | null>(null);
  const [lichSuNhap, setLichSuNhap] = useState<string[]>([]);

  /**
   * Tự động nối tiếp ra ngoài khi tài liệu không có câu trả lời — US-032.
   *
   * Cố ý **không** lưu vào `localStorage`. Đây là công tắc quyết định dữ liệu
   * có rời khỏi máy hay không; một công tắc như vậy mà tự bật lại ở lần mở
   * trang sau thì người dùng sẽ có lúc gửi câu hỏi ra ngoài mà không nhớ là
   * mình đã cho phép. Bật lại mỗi phiên làm việc là một cái giá nhỏ, đổi lấy
   * việc US-032 AC-2 luôn đúng ở trạng thái mặc định.
   */
  const [tuDongNgoai, setTuDongNgoai] = useState(false);
  /** Đã qua hộp xác nhận của Privacy Mode trong lần mở trang này (AC-4). */
  const daXacNhanNgoai = useRef(false);

  const cuoiRef = useRef<HTMLDivElement>(null);
  const oNhapRef = useRef<HTMLTextAreaElement>(null);
  // Giá trị mới nhất, đọc được từ trong một hàm async đang chạy dở — state của
  // React thì đóng băng theo lượt vẽ đã tạo ra hàm đó.
  const phienIdRef = useRef<string | null>(null);
  const dangHoiRef = useRef(false);
  const nguonRef = useRef<Nguon[]>(nguon);
  const huyRef = useRef<AbortController | null>(null);
  const { t } = useNgonNgu();
  const tuyChon = useTuyChon();

  useEffect(() => {
    nguonRef.current = nguon;
  }, [nguon]);

  const datPhien = useCallback(
    (id: string | null) => {
      phienIdRef.current = id;
      setPhienId(id);
      onDoiPhien?.(id);
    },
    [onDoiPhien],
  );

  const taiPhien = useCallback(
    async (id: string) => {
      const tin = await api.tinNhanCuaPhien(id);
      datPhien(id);
      setLuot(tuTinNhan(tin));
    },
    [datPhien],
  );

  // ── Khôi phục phiên gần nhất — US-018 AC-3 ──────────
  useEffect(() => {
    let huy = false;
    setDangTaiLichSu(true);
    setLuot([]);
    datPhien(null);
    setTuDongNgoai(false);
    daXacNhanNgoai.current = false;
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
  }, [nbId, taiPhien, datPhien]);

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

  // Ảnh đính kèm giữ một URL blob; không thu hồi thì trình duyệt giữ nguyên
  // cả tấm ảnh trong bộ nhớ cho tới khi rời trang.
  useEffect(() => {
    return () => {
      for (const dk of dinhKem) URL.revokeObjectURL(dk.url);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
        datPhien(String(e.session_id));
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

  /**
   * Chạy một lượt hỏi và trả về kết cục.
   *
   * Cả hai đường — có căn cứ và hỏi ngoài — đi qua đây, nên việc dừng giữa
   * chừng, khoá nút và đóng lượt chỉ được viết một lần.
   */
  async function chay(
    q: string,
    duong: string,
    than: Record<string, unknown>,
  ): Promise<KetCuc> {
    const bo = new AbortController();
    huyRef.current = bo;
    dangHoiRef.current = true;
    setDangHoi(true);

    const capNhat = themLuot(q);
    let tuChoi = false;
    let canXacNhan = false;

    await hoi(
      than,
      (ev) => {
        if (ev.type === "confirm_required") {
          canXacNhan = true;
          return;
        }
        if (ev.type === "no_answer") tuChoi = true;
        xuLy(capNhat, ev);
      },
      duong,
      bo.signal,
    );

    const huy = bo.signal.aborted;
    if (huy) {
      // Máy chủ vẫn ghi câu trả lời đầy đủ vào lịch sử; thứ dừng lại là việc
      // hiển thị. Đánh dấu rõ để người dùng không tưởng mô hình bị cụt.
      capNhat((l) => ({ ...l, xong: true, trangThai: null, daDung: true }));
    }

    huyRef.current = null;
    dangHoiRef.current = false;
    setDangHoi(false);
    return { tuChoi, huy, canXacNhan };
  }

  function dungLai() {
    huyRef.current?.abort();
  }

  // ── Ảnh dán vào ô câu hỏi — US-025 ──────────────────
  //
  // Ảnh chỉ trở thành nguồn khi người dùng bấm gửi, không phải ngay lúc dán:
  // dán nhầm rồi phải vào cột nguồn xoá đi là một sự khó chịu không cần thiết.

  function themDinhKem(files: File[]) {
    setDinhKem((cu) => [
      ...cu,
      ...files.map((file) => ({
        id: `${file.name}-${cu.length}-${file.size}`,
        file,
        url: URL.createObjectURL(file),
      })),
    ]);
  }

  function boDinhKem(id: string) {
    setDinhKem((cu) => {
      const bo = cu.find((d) => d.id === id);
      if (bo) URL.revokeObjectURL(bo.url);
      return cu.filter((d) => d.id !== id);
    });
  }

  /** Đợi các nguồn vừa tải lên chạy xong pipeline nạp tài liệu.
   *
   *  Đọc từ danh sách nguồn mà trang cha đã theo dõi sẵn bằng SSE (US-022) chứ
   *  không mở thêm một vòng hỏi lại của riêng mình — hai nguồn sự thật cho cùng
   *  một trạng thái là cách chắc chắn để chúng lệch nhau. */
  async function doiXuLyXong(ids: string[]): Promise<void> {
    const han = Date.now() + CHO_ANH_MS;
    for (;;) {
      const cua = nguonRef.current.filter((s) => ids.includes(s.id));
      const xongHet =
        cua.length === ids.length && cua.every((s) => TRANG_THAI_CUOI.has(s.status));
      if (xongHet) {
        if (cua.some((s) => s.status === "failed")) throw new Error("anh-hong");
        return;
      }
      if (Date.now() > han) throw new Error("anh-lau");
      await new Promise((r) => setTimeout(r, 1200));
      // Nhắc trang cha nạp lại: nếu luồng SSE đã đóng thì đây là thứ đánh thức
      // nó dậy, và cũng là lưới an toàn khi một sự kiện bị rơi.
      onThemNguon();
    }
  }

  /** Đưa ảnh đính kèm vào nguồn và đợi chúng hỏi được. */
  async function napDinhKem(ds: DinhKem[]): Promise<void> {
    const ids: string[] = [];
    for (const dk of ds) {
      setTrangThaiAnh(t("chat.dangTaiAnh", { ten: dk.file.name }));
      const n = await taiLen(nbId, dk.file, () => {});
      ids.push(n.id);
    }
    onThemNguon();
    setTrangThaiAnh(t("chat.dangXuLyAnh"));
    await doiXuLyXong(ids);
  }

  function loiAnh(err: unknown): string {
    if (err instanceof ApiError) return err.message;
    if (err instanceof Error && err.message === "anh-lau") return t("chat.anhLau");
    if (err instanceof Error && err.message === "anh-hong") return t("chat.anhHong");
    return t("chat.anhKhongTaiDuoc");
  }

  // ── Lịch sử ô nhập cho phím ↑ ───────────────────────

  const viTriLichSu = useRef<number | null>(null);
  const banNhap = useRef("");

  useEffect(() => {
    try {
      const luu = JSON.parse(localStorage.getItem(`documind.danhap.${nbId}`) ?? "[]");
      if (Array.isArray(luu)) setLichSuNhap(luu.filter((x) => typeof x === "string"));
    } catch {
      /* dữ liệu cũ hỏng thì bắt đầu trống */
    }
    viTriLichSu.current = null;
    banNhap.current = "";
  }, [nbId]);

  function ghiLichSuNhap(q: string) {
    setLichSuNhap((cu) => {
      // Hỏi lại y hệt câu vừa hỏi là chuyện thường; giữ hai bản giống nhau
      // liền nhau chỉ làm phím ↑ phải bấm hai lần cho cùng một câu.
      const moi = cu[cu.length - 1] === q ? cu : [...cu, q];
      const cat = moi.slice(-LICH_SU_NHAP_TOI_DA);
      try {
        localStorage.setItem(`documind.danhap.${nbId}`, JSON.stringify(cat));
      } catch {
        /* chỉ sống trong phiên này */
      }
      return cat;
    });
    viTriLichSu.current = null;
    banNhap.current = "";
  }

  function datConTroCuoi() {
    requestAnimationFrame(() => {
      const o = oNhapRef.current;
      if (!o) return;
      o.selectionStart = o.selectionEnd = o.value.length;
    });
  }

  /**
   * ↑ / ↓ đi lại trong các câu đã hỏi, kiểu dòng lệnh.
   *
   * Chỉ cướp phím khi con trỏ đang ở dòng đầu (với ↑) hoặc dòng cuối (với ↓).
   * Không có điều kiện đó thì người dùng không di chuyển được bên trong một câu
   * hỏi nhiều dòng — phím mũi tên là phím soạn thảo trước khi là phím tắt.
   */
  function phimLichSu(e: React.KeyboardEvent<HTMLTextAreaElement>): boolean {
    const o = e.currentTarget;
    if (o.selectionStart !== o.selectionEnd) return false;

    if (e.key === "ArrowUp") {
      if (!lichSuNhap.length) return false;
      if (o.value.slice(0, o.selectionStart).includes("\n")) return false;
      if (viTriLichSu.current === null) {
        banNhap.current = o.value;
        viTriLichSu.current = lichSuNhap.length;
      }
      viTriLichSu.current = Math.max(0, viTriLichSu.current - 1);
      setCauHoi(lichSuNhap[viTriLichSu.current]);
      datConTroCuoi();
      return true;
    }

    if (e.key === "ArrowDown") {
      if (viTriLichSu.current === null) return false;
      if (o.value.slice(o.selectionEnd).includes("\n")) return false;
      const tiep = viTriLichSu.current + 1;
      if (tiep >= lichSuNhap.length) {
        viTriLichSu.current = null;
        setCauHoi(banNhap.current);
      } else {
        viTriLichSu.current = tiep;
        setCauHoi(lichSuNhap[tiep]);
      }
      datConTroCuoi();
      return true;
    }

    return false;
  }

  // ── Gửi ─────────────────────────────────────────────

  async function gui() {
    if (dangHoiRef.current || trangThaiAnh !== null) return;
    const q = cauHoi.trim();
    if (!q && !dinhKem.length) return;

    setThongBao(null);

    if (dinhKem.length) {
      const ds = dinhKem;
      try {
        await napDinhKem(ds);
        setDinhKem((cu) => cu.filter((d) => !ds.includes(d)));
        for (const dk of ds) URL.revokeObjectURL(dk.url);
      } catch (err) {
        setThongBao(loiAnh(err));
        return;
      } finally {
        setTrangThaiAnh(null);
      }
    }

    // Dán ảnh mà không gõ gì là "thêm tài liệu này vào nguồn", không phải một
    // câu hỏi. Thêm xong là xong.
    if (!q) {
      oNhapRef.current?.focus();
      return;
    }

    setCauHoi("");
    ghiLichSuNhap(q);

    const kq = await chay(q, "/api/chat/ask", {
      question: q,
      notebook_id: nbId,
      session_id: phienIdRef.current,
    });

    // Nối tiếp ra ngoài, nếu người dùng đã bật công tắc — US-032 AC-1.
    if (kq.tuChoi && !kq.huy && tuDongNgoai) {
      await hoiNgoai(q);
    }
    oNhapRef.current?.focus();
  }

  /**
   * Hỏi bằng kiến thức ngoài tài liệu — US-032.
   *
   * Ở Privacy Mode máy chủ trả `confirm_required` trước; giao diện hỏi lại
   * người dùng rồi gọi tiếp với `confirmed: true`. Câu trả lời hiện thành một
   * lượt riêng, đóng khung khác (US-033 AC-1).
   */
  async function hoiNgoai(q: string, vuaXacNhan = false) {
    if (dangHoiRef.current) return;
    setHoiXacNhanNgoai(null);

    const kq = await chay(q, "/api/chat/ask-external", {
      question: q,
      notebook_id: nbId,
      session_id: phienIdRef.current,
      confirmed: vuaXacNhan || daXacNhanNgoai.current,
    });

    if (kq.canXacNhan) {
      // Bỏ lượt trống vừa thêm; hộp xác nhận sẽ gọi lại khi người dùng đồng ý.
      setLuot((cu) => cu.slice(0, -1));
      setHoiXacNhanNgoai(q);
    }
  }

  function hoiThoaiMoi() {
    if (dangHoiRef.current) return;
    setLuot([]);
    datPhien(null);
    setThongBao(null);
    oNhapRef.current?.focus();
  }

  async function doiPhien(id: string) {
    if (dangHoiRef.current || id === phienId) return;
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
  const dangBan = dangHoi || trangThaiAnh !== null;
  const guiDuoc = (cauHoi.trim().length > 0 || dinhKem.length > 0) && !dangBan;

  return (
    <div className="flex h-full flex-col bg-nen">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-vien bg-the/60 px-5 py-2">
        <button
          onClick={hoiThoaiMoi}
          disabled={dangBan}
          className="nut-phu"
          title={t("chat.hoiThoaiMoi")}
        >
          <Bt.them size={14} /> {t("chat.hoiThoaiMoi")}
        </button>

        {phienDs.length > 0 && (
          <select
            value={phienId ?? ""}
            onChange={(e) => e.target.value && void doiPhien(e.target.value)}
            disabled={dangBan}
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

        <div className="ml-auto flex items-center gap-2">
          <CongTacNgoai bat={tuDongNgoai} onDoi={setTuDongNgoai} />
          {/* Xuất — một nút, hai lựa chọn; chỉ hiện khi đã có gì để xuất (US-040). */}
          {coGiDeXuat && <MenuXuat dangXuat={dangXuat} onXuat={(d) => void xuat(d)} />}
        </div>
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
          <div className={`${RONG_DOC} rounded-2xl border border-dashed border-vien px-6 py-12 text-center`}>
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

        <div className={`${RONG_DOC} space-y-8`}>
          {luot.map((l, i) =>
            // Lượt từ chối đã được nối tiếp ra ngoài thì không vẽ riêng: cùng
            // một câu hỏi hiện hai lần liền nhau đọc như người dùng lỡ tay gõ
            // lại. Nó gộp vào một dòng nhỏ trên câu trả lời ngoài.
            biNoiTiep(luot, i) ? null : (
              <LuotHoiDap
                key={i}
                l={l}
                cuoi={i === luot.length - 1}
                dangHoi={dangBan}
                hienMoHinh={tuyChon.hienMoHinh}
                tuDongNgoai={tuDongNgoai}
                noiTiep={biNoiTiep(luot, i - 1)}
                onChonTrichDan={onChonTrichDan}
                onHoiNgoai={() => void hoiNgoai(l.cauHoi)}
              />
            ),
          )}
          <div ref={cuoiRef} />
        </div>
      </div>

      {/* Xác nhận trước khi gửi câu hỏi ra ngoài ở Privacy Mode — US-032 AC-4. */}
      {hoiXacNhanNgoai && (
        <div className="shrink-0 border-t border-canh-bao bg-canh-bao-nen px-6 py-3">
          <div className={`${RONG_DOC} flex flex-wrap items-center gap-3`}>
            <p className="flex-1 text-sm text-canh-bao">{t("chat.xacNhanNgoai")}</p>
            <button
              onClick={() => {
                daXacNhanNgoai.current = true;
                void hoiNgoai(hoiXacNhanNgoai, true);
              }}
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
        className="shrink-0 border-t border-vien bg-the/60 px-5 py-3 sm:px-8"
      >
        <div className={RONG_DOC}>
          <div className="o-nhap">
            {dinhKem.length > 0 && (
              <ul className="flex flex-wrap gap-2 border-b border-vien px-3 py-2.5">
                {dinhKem.map((dk) => (
                  <li key={dk.id} className="dinh-kem">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={dk.url} alt={dk.file.name} />
                    <button
                      type="button"
                      onClick={() => boDinhKem(dk.id)}
                      title={t("chat.boDinhKem")}
                      className="dinh-kem-bo"
                    >
                      <Bt.dong size={11} />
                      <span className="sr-only">{t("chat.boDinhKem")}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="flex items-end gap-2 px-1 py-1">
              <textarea
                ref={oNhapRef}
                rows={1}
                value={cauHoi}
                onChange={(e) => {
                  setCauHoi(e.target.value);
                  viTriLichSu.current = null;
                }}
                onPaste={(e) => {
                  const anh = anhTuClipboard(e.clipboardData);
                  // Dán chữ thì để trình duyệt làm việc của nó.
                  if (!anh.length) return;
                  e.preventDefault();
                  themDinhKem(anh);
                }}
                onKeyDown={(e) => {
                  if (phimLichSu(e)) {
                    e.preventDefault();
                    return;
                  }
                  // Enter gửi; Shift+Enter xuống dòng — quy ước quen thuộc của
                  // mọi khung chat, và câu hỏi hiếm khi cần nhiều dòng.
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    void gui();
                  }
                }}
                placeholder={sanSang ? t("chat.oNhap") : t("chat.chuaSanSang")}
                className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2.5 py-2 text-[15px] leading-relaxed outline-none placeholder:text-mo/70"
              />

              {/* Trong lúc câu trả lời đang chảy về, cùng một vị trí đổi thành
                  nút dừng: người dùng nhận ra prompt chưa đúng ý ngay khi đọc
                  dòng đầu tiên, và họ cần dừng chứ không cần đợi cho xong. */}
              {dangHoi ? (
                <button
                  type="button"
                  onClick={dungLai}
                  className="nut-gui nut-dung"
                  title={t("chat.dung")}
                >
                  <Bt.dung size={14} />
                  <span className="sr-only">{t("chat.dung")}</span>
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!guiDuoc}
                  className="nut-gui"
                  aria-label={t("chat.hoi")}
                >
                  {trangThaiAnh !== null ? (
                    <span className="dang-cho" aria-hidden="true" />
                  ) : (
                    <Bt.gui size={16} />
                  )}
                </button>
              )}
            </div>
          </div>

          {trangThaiAnh !== null ? (
            <p role="status" className="mt-1.5 flex items-center gap-2 text-[11px] text-mo">
              <span className="dang-cho" aria-hidden="true" />
              {trangThaiAnh}
            </p>
          ) : (
            <p className="mt-1.5 text-[11px] text-mo/70">
              {t("chat.goiYPhim")}
              {/* Trên màn hình điện thoại dòng này chiếm hai dòng và đẩy ô nhập
                  lên; hai mẹo sau là tiện ích của bàn phím, nơi không có bàn
                  phím thì cũng không dùng tới. */}
              <span className="hidden sm:inline">{t("chat.goiYPhimThem")}</span>
            </p>
          )}
        </div>
      </form>
    </div>
  );
}

/**
 * Công tắc "tự động hỏi ra ngoài" — US-032 AC-1.
 *
 * Là một công tắc chứ không phải một nút bấm mỗi lượt, vì đây là một quyết định
 * về *cách làm việc* chứ không phải về một câu hỏi cụ thể. Nhưng nó vẫn phải là
 * một hành động có ý thức: mặc định tắt, nhãn nói thẳng dữ liệu sẽ đi đâu, và
 * trạng thái bật nhìn thấy được suốt cuộc hội thoại chứ không nấp trong menu.
 */
function CongTacNgoai({ bat, onDoi }: { bat: boolean; onDoi: (v: boolean) => void }) {
  const { t } = useNgonNgu();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={bat}
      onClick={() => onDoi(!bat)}
      title={t("chat.tuDongNgoaiMoTa")}
      className={`cong-tac ${bat ? "cong-tac-bat" : ""}`}
    >
      <Bt.toanCau size={13} />
      <span className="hidden sm:inline">{t("chat.tuDongNgoai")}</span>
      <span className="cong-tac-den" aria-hidden="true" />
    </button>
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
    <div className="relative">
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
  hienMoHinh,
  tuDongNgoai,
  noiTiep,
  onChonTrichDan,
  onHoiNgoai,
}: {
  l: Luot;
  cuoi: boolean;
  dangHoi: boolean;
  hienMoHinh: boolean;
  tuDongNgoai: boolean;
  /** Lượt này trả lời hộ một lượt từ chối ngay trước đó — US-032. */
  noiTiep: boolean;
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

      {/* Vì sao câu trả lời này không đến từ tài liệu — thay cho cả một lượt
          từ chối riêng, nhưng vẫn nói đúng chuyện đã xảy ra. */}
      {noiTiep && (
        <p className="mt-3 text-xs italic text-mo">{t("chat.khongCoTrongTaiLieu")}</p>
      )}

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
        ) : l.daDung ? (
          <p className="text-sm italic text-mo">{t("chat.daDungTruocKhiTraLoi")}</p>
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
          {l.daDung && l.traLoi && <span>{t("chat.daDung")}</span>}
          {/* Tên mô hình là thứ chỉ người vận hành quan tâm — mặc định ẩn,
              bật lại trong Cài đặt (US-030 AC-3). */}
          {hienMoHinh && tenMoHinh(l.moHinh) && (
            <span className="tabular-nums">{tenMoHinh(l.moHinh)}</span>
          )}
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

      {/* Mời hỏi ra ngoài — chỉ sau khi cổng ngưỡng đã từ chối (US-032 AC-1).
          Công tắc bật rồi thì việc này đã tự xảy ra, nút chỉ còn là nhiễu. */}
      {l.xong && l.tuChoi && !l.ngoai && cuoi && !dangHoi && !tuDongNgoai && (
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
