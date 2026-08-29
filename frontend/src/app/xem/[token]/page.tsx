"use client";

/**
 * Trang xem một đoạn hội thoại được chia sẻ — US-039, quyết định 0004.
 *
 * Không đăng nhập thì **đọc**: đoạn hỏi đáp đã được chia sẻ, chip trích dẫn bấm
 * được, và cột phải mở đúng trang tài liệu kèm vùng tô sáng. Muốn **hỏi** thì
 * phải đăng nhập, và câu hỏi đi vào lịch sử của chính người hỏi.
 *
 * Trang này tồn tại riêng thay vì dùng lại màn hình làm việc với vài chỗ bị ẩn
 * đi: ẩn nút thì mã bên dưới vẫn còn, và một tính năng mới thêm vào màn hình
 * kia sẽ tự động lộ ra ở đây. Cột xem tài liệu thì ngược lại — nó được dùng
 * chung, vì nó chỉ đọc theo bản chất và vì trích dẫn không kiểm chứng được nếu
 * người xem không mở được tài liệu.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  GOC_API,
  type NotebookChiaSe,
  type TinNhanChiaSe,
  type TrichDan,
  api,
  token as kho,
} from "@/lib/api";
import { nguonChiaSe } from "@/lib/nguonXem";
import { type SuKien } from "@/lib/stream";
import { CotTaiLieu } from "@/components/CotTaiLieu";
import { MenuCaiDat } from "@/components/MenuCaiDat";
import { useNgonNgu } from "@/components/NgonNguProvider";
import { VanBanTraLoi } from "@/components/VanBanTraLoi";
import { Bt } from "@/components/BieuTuong";
import type { Khoa } from "@/lib/i18n";

type Luot = {
  cauHoi: string;
  traLoi: string;
  trichDan: Record<number, TrichDan>;
  markerChet: Set<number>;
  trangThai: string | null;
  xong: boolean;
  loi: string | null;
};

const KHOA_BUOC: Record<string, Khoa> = {
  retrieving: "buoc.retrieving",
  reranking: "buoc.reranking",
  generating: "buoc.generating",
};

function luotMoi(cauHoi: string): Luot {
  return {
    cauHoi,
    traLoi: "",
    trichDan: {},
    markerChet: new Set(),
    trangThai: null,
    xong: false,
    loi: null,
  };
}

/** Tin nhắn đã lưu → các lượt hiển thị. Cùng phép biến đổi với cột hỏi đáp. */
function tuTinNhan(ds: TinNhanChiaSe[]): Luot[] {
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
    out[out.length - 1] = { ...l, traLoi: m.content, trichDan, markerChet: chet, xong: true };
  }
  return out;
}

export default function TrangXemChiaSe() {
  const { token } = useParams<{ token: string }>();
  const [nb, setNb] = useState<NotebookChiaSe | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [goc, setGoc] = useState<Luot[]>([]);
  const [luot, setLuot] = useState<Luot[]>([]);
  const [phienId, setPhienId] = useState<string | null>(null);
  const [cauHoi, setCauHoi] = useState("");
  const [dangHoi, setDangHoi] = useState(false);
  const [daDangNhap, setDaDangNhap] = useState(false);
  const [trichDan, setTrichDan] = useState<TrichDan | null>(null);
  const cuoiRef = useRef<HTMLDivElement>(null);
  const { t, soTrang } = useNgonNgu();

  // Ổn định qua các lượt vẽ — `CotTaiLieu` dùng nó trong mảng phụ thuộc.
  const nguon = useMemo(() => nguonChiaSe(token), [token]);

  useEffect(() => {
    setDaDangNhap(Boolean(kho.access()));
  }, []);

  useEffect(() => {
    api
      .notebookChiaSe(token)
      .then((d) => {
        setNb(d);
        setGoc(tuTinNhan(d.tin_nhan));
      })
      .catch(() => setLoi(t("chiaSe.hetHieuLuc")));
  }, [token]);

  // Người xem đã từng hỏi qua liên kết này thì mở lại đúng chỗ họ bỏ dở.
  useEffect(() => {
    if (!daDangNhap) return;
    let huy = false;
    (async () => {
      try {
        const ds = await api.phienCuaToiTrongChiaSe(token);
        if (huy || ds.length === 0) return;
        const tin = await api.tinNhanCuaToiTrongChiaSe(token, ds[0].id);
        if (huy) return;
        setPhienId(ds[0].id);
        setLuot(tuTinNhan(tin));
      } catch {
        /* chưa hỏi gì qua liên kết này — bắt đầu trống, không phải lỗi */
      }
    })();
    return () => {
      huy = true;
    };
  }, [daDangNhap, token]);

  useEffect(() => {
    if (luot.length) cuoiRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [luot]);

  const chonTrichDan = useCallback((c: TrichDan) => setTrichDan(c), []);

  async function gui(e: React.FormEvent) {
    e.preventDefault();
    const q = cauHoi.trim();
    if (!q || dangHoi) return;

    setCauHoi("");
    setDangHoi(true);
    const chiSo = luot.length;
    setLuot((cu) => [...cu, luotMoi(q)]);
    const capNhat = (sua: (l: Luot) => Luot) =>
      setLuot((cu) => cu.map((l, i) => (i === chiSo ? sua(l) : l)));

    try {
      // Không đi qua `hoi()` của `lib/stream`: hàm đó gắn `notebook_id`, mà ở
      // đây quyền đi theo token trong đường dẫn chứ không theo notebook.
      const at = kho.access();
      const r = await fetch(`${GOC_API}/api/shared/${token}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(at ? { Authorization: `Bearer ${at}` } : {}),
        },
        body: JSON.stringify({ question: q, session_id: phienId }),
      });
      if (!r.ok || !r.body) throw new Error(String(r.status));

      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let dem = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        dem += decoder.decode(value, { stream: true });
        const goi = dem.split("\n\n");
        dem = goi.pop() ?? "";
        for (const g of goi) {
          if (!g.startsWith("data: ")) continue;
          let e: SuKien;
          try {
            e = JSON.parse(g.slice(6)) as SuKien;
          } catch {
            continue;
          }
          switch (e.type) {
            case "session":
              setPhienId(String(e.session_id));
              break;
            case "status":
              capNhat((l) => ({
                ...l,
                trangThai:
                  String(e.stage) in KHOA_BUOC ? t(KHOA_BUOC[String(e.stage)]) : null,
              }));
              break;
            case "token":
              capNhat((l) => ({ ...l, traLoi: l.traLoi + String(e.text) }));
              break;
            case "replace":
              capNhat((l) => ({ ...l, traLoi: String(e.text) }));
              break;
            case "citation":
              capNhat((l) => ({
                ...l,
                trichDan: { ...l.trichDan, [Number(e.marker)]: e as unknown as TrichDan },
              }));
              break;
            case "error":
              capNhat((l) => ({ ...l, loi: String(e.message), xong: true }));
              break;
            case "done":
              capNhat((l) => ({ ...l, xong: true, trangThai: null }));
              break;
          }
        }
      }
    } catch {
      capNhat((l) => ({ ...l, loi: t("auth.khongKetNoi"), xong: true }));
    } finally {
      setDangHoi(false);
    }
  }

  if (loi) {
    return (
      <main className="grid h-full place-items-center px-6 text-center">
        <div>
          <p className="font-medium">{loi}</p>
          <p className="mt-1 text-sm text-mo">{t("chiaSe.xinLienKetMoi")}</p>
        </div>
      </main>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-vien px-5 py-3">
        <div className="min-w-0">
          <p className="truncate font-medium tracking-tight">
            {nb?.phien_tieu_de ?? nb?.title ?? "…"}
          </p>
          {nb?.phien_tieu_de && (
            <p className="truncate text-xs text-mo">{nb.title}</p>
          )}
        </div>
        <span className="rounded-md border border-vien px-1.5 py-0.5 text-[11px] text-mo">
          {t("chiaSe.chiDoc")}
        </span>
        <div className="ml-auto">
          <MenuCaiDat taiKhoan={daDangNhap} />
        </div>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[240px_1fr_380px]">
        <aside className="hidden overflow-y-auto border-r border-vien bg-the lg:block">
          <p className="border-b border-vien px-4 py-3 text-xs font-semibold uppercase tracking-wider text-mo">
            {t("cot.taiLieu")}
          </p>
          <ul>
            {(nb?.nguon ?? []).map((s) => (
              <li key={s.id} className="border-b border-vien px-4 py-3">
                <p className="truncate text-sm font-medium">{s.title}</p>
                <p className="mt-0.5 text-xs text-mo">
                  {s.kind.toUpperCase()}
                  {s.kind !== "image" && s.page_count ? ` · ${soTrang(s.page_count)}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </aside>

        <section className="flex min-h-0 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
            <div className="mx-auto max-w-[68ch] space-y-7">
              {goc.map((l, i) => (
                <KhoiLuot key={`goc-${i}`} luot={l} onChon={chonTrichDan} />
              ))}

              {goc.length === 0 && (
                <div className="rounded-lg border border-dashed border-vien px-5 py-10 text-center">
                  <p className="font-medium">{t("chat.batDau")}</p>
                  <p className="mt-1 text-sm text-mo">{t("chat.batDauMoTa")}</p>
                </div>
              )}

              {luot.length > 0 && (
                <p className="border-t border-vien pt-5 text-xs font-semibold uppercase tracking-wider text-mo">
                  {t("chiaSe.hoiThemCuaToi")}
                </p>
              )}
              {luot.map((l, i) => (
                <KhoiLuot key={`toi-${i}`} luot={l} onChon={chonTrichDan} />
              ))}
              <div ref={cuoiRef} />
            </div>
          </div>

          {daDangNhap ? (
            <form onSubmit={gui} className="shrink-0 border-t border-vien px-6 py-4">
              <div className="mx-auto flex max-w-[68ch] gap-2">
                <input
                  value={cauHoi}
                  onChange={(e) => setCauHoi(e.target.value)}
                  disabled={dangHoi}
                  placeholder={t("chat.oNhap")}
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
          ) : (
            <div className="shrink-0 border-t border-vien px-6 py-4">
              <div className="mx-auto flex max-w-[68ch] items-center gap-3 rounded-lg border border-vien bg-the px-4 py-3">
                <Bt.khoa size={16} className="shrink-0 text-mo" />
                <p className="min-w-0 flex-1 text-xs text-mo">
                  {t("chiaSe.dangNhapMoTa")}
                </p>
                <Link
                  href={`/?tiep=${encodeURIComponent(`/xem/${token}`)}`}
                  className="shrink-0 rounded-md bg-nhan px-4 py-2 text-sm font-medium text-nen"
                >
                  {t("chiaSe.dangNhapDeHoi")}
                </Link>
              </div>
            </div>
          )}
        </section>

        <aside className="hidden min-h-0 border-l border-vien bg-the lg:block">
          <CotTaiLieu nguon={nguon} trichDan={trichDan} />
        </aside>
      </div>
    </div>
  );
}

function KhoiLuot({ luot, onChon }: { luot: Luot; onChon: (c: TrichDan) => void }) {
  const { t } = useNgonNgu();
  return (
    <div>
      <p className="text-sm text-mo">
        <b className="font-semibold text-chu">{t("chat.ban")}</b> {luot.cauHoi}
      </p>
      <div
        className={`mt-2 rounded-2xl border px-5 py-4 ${
          luot.loi ? "border-canh-bao bg-canh-bao-nen" : "border-vien bg-the"
        }`}
      >
        {luot.loi ? (
          luot.loi
        ) : luot.traLoi ? (
          <VanBanTraLoi
            text={luot.traLoi}
            trichDan={luot.trichDan}
            markerChet={luot.markerChet}
            onChon={onChon}
          />
        ) : (
          <span className="text-sm italic text-mo">
            {luot.trangThai ?? t("chung.dangXuLy")}…
          </span>
        )}
      </div>
    </div>
  );
}
