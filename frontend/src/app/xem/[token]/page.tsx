"use client";

/**
 * Trang xem một notebook được chia sẻ — US-039 AC-2.
 *
 * Không đăng nhập, không token, không có gì để làm ngoài đọc và hỏi. Đó là lý
 * do trang này tồn tại riêng thay vì dùng lại màn hình làm việc với vài chỗ bị
 * ẩn đi: ẩn nút thì mã bên dưới vẫn còn, và một tính năng mới thêm vào màn hình
 * kia sẽ tự động lộ ra ở đây.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { GOC_API, type NotebookChiaSe, api } from "@/lib/api";
import { type SuKien } from "@/lib/stream";
import { NutChuDe } from "@/components/NutChuDe";
import { NutNgonNgu, useNgonNgu } from "@/components/NgonNguProvider";
import type { Khoa } from "@/lib/i18n";

type Luot = {
  cauHoi: string;
  traLoi: string;
  trichDan: Record<number, { marker: number; chunk_id: number; snippet: string }>;
  trangThai: string | null;
  xong: boolean;
  loi: string | null;
};

const KHOA_BUOC: Record<string, Khoa> = {
  retrieving: "buoc.retrieving",
  reranking: "buoc.reranking",
  generating: "buoc.generating",
};

export default function TrangXemChiaSe() {
  const { token } = useParams<{ token: string }>();
  const [nb, setNb] = useState<NotebookChiaSe | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [luot, setLuot] = useState<Luot[]>([]);
  const [cauHoi, setCauHoi] = useState("");
  const [dangHoi, setDangHoi] = useState(false);
  const [doan, setDoan] = useState<{ title: string; content: string } | null>(null);
  const cuoiRef = useRef<HTMLDivElement>(null);
  const { t } = useNgonNgu();

  useEffect(() => {
    api
      .notebookChiaSe(token)
      .then(setNb)
      .catch(() => setLoi(t("chiaSe.hetHieuLuc")));
  }, [token]);

  useEffect(() => {
    cuoiRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [luot]);

  const moDoan = useCallback(
    async (chunkId: number) => {
      const r = await fetch(`${GOC_API}/api/shared/${token}/citations/${chunkId}`);
      if (!r.ok) return;
      const d = await r.json();
      setDoan({ title: d.source.title, content: d.content });
    },
    [token],
  );

  async function gui(e: React.FormEvent) {
    e.preventDefault();
    const q = cauHoi.trim();
    if (!q || dangHoi) return;

    setCauHoi("");
    setDangHoi(true);
    const chiSo = luot.length;
    setLuot((cu) => [
      ...cu,
      { cauHoi: q, traLoi: "", trichDan: {}, trangThai: null, xong: false, loi: null },
    ]);
    const capNhat = (sua: (l: Luot) => Luot) =>
      setLuot((cu) => cu.map((l, i) => (i === chiSo ? sua(l) : l)));

    try {
      // Không đi qua `hoi()` của `lib/stream`: hàm đó gắn `Authorization`, mà ở
      // đây không có phiên đăng nhập nào để gắn.
      const r = await fetch(`${GOC_API}/api/shared/${token}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
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
            case "status":
              capNhat((l) => ({
                ...l,
                trangThai:
                  String(e.stage) in KHOA_BUOC
                    ? t(KHOA_BUOC[String(e.stage)])
                    : null,
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
                trichDan: {
                  ...l.trichDan,
                  [Number(e.marker)]: e as unknown as Luot["trichDan"][number],
                },
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
          <p className="mt-1 text-sm text-mo">
            {t("chiaSe.xinLienKetMoi")}
          </p>
        </div>
      </main>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-vien px-5 py-3">
        <span className="font-medium tracking-tight">{nb?.title ?? "…"}</span>
        <span className="rounded-md border border-vien px-1.5 py-0.5 text-[11px] text-mo">
          {t("chiaSe.chiDoc")}
        </span>
        <div className="ml-auto flex items-center gap-3">
          <NutNgonNgu />
          <NutChuDe />
        </div>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[260px_1fr_320px]">
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
                  {s.kind !== "image" && s.page_count ? ` · ${s.page_count} ${t("chung.trang")}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </aside>

        <section className="flex min-h-0 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
            {luot.length === 0 && (
              <div className="mx-auto max-w-[68ch] rounded-lg border border-dashed border-vien px-5 py-10 text-center">
                <p className="font-medium">{t("chat.batDau")}</p>
                <p className="mt-1 text-sm text-mo">
                  {t("chat.batDauMoTa")}
                </p>
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
                      l.loi ? "border-canh-bao bg-canh-bao-nen" : "border-vien bg-the"
                    }`}
                  >
                    {l.loi ? (
                      l.loi
                    ) : l.traLoi ? (
                      <VanBanCoChip text={l.traLoi} trichDan={l.trichDan} onChon={moDoan} />
                    ) : (
                      <span className="text-sm italic text-mo">
                        {l.trangThai ?? t("chung.dangXuLy")}…
                      </span>
                    )}
                  </div>
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
        </section>

        <aside className="hidden overflow-y-auto border-l border-vien bg-the p-4 lg:block">
          <p className="text-xs font-semibold uppercase tracking-wider text-mo">
            {t("xem.doanTrichDan")}
          </p>
          {doan ? (
            <>
              <p className="mt-3 text-sm font-semibold">{doan.title}</p>
              <pre className="mt-2 whitespace-pre-wrap rounded-md border border-vien bg-nen p-3 text-[13px] leading-relaxed">
                {doan.content}
              </pre>
            </>
          ) : (
            <p className="mt-3 text-xs text-mo">
              {t("xem.huongDanChip")}
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}

function VanBanCoChip({
  text,
  trichDan,
  onChon,
}: {
  text: string;
  trichDan: Luot["trichDan"];
  onChon: (chunkId: number) => void;
}) {
  const phan = text.split(/(\[\d{1,2}\])/g);
  return (
    <>
      {phan.map((p, i) => {
        const m = /^\[(\d{1,2})\]$/.exec(p);
        if (!m) return <span key={i}>{p}</span>;
        const so = Number(m[1]);
        const t = trichDan[so];
        if (!t) return <span key={i} className="chip chip-chet">{so}</span>;
        return (
          <button key={i} className="chip" title={t.snippet} onClick={() => onChon(t.chunk_id)}>
            {so}
          </button>
        );
      })}
    </>
  );
}
