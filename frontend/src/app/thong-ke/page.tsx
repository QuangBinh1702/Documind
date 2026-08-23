"use client";

/**
 * Trang thống kê — US-041.
 *
 * Trang này có hai người đọc, và đó là lý do nó trông như bây giờ: người vận
 * hành muốn biết hệ thống đang chạy ra sao, còn người bảo vệ đồ án cần một hình
 * dán thẳng vào slide (AC-5).
 *
 * Biểu đồ vẽ bằng SVG viết tay, không kéo thư viện đồ thị nào. Ba lý do: các
 * hình ở đây đơn giản (một cột, một vòng), một thư viện đồ thị nặng hơn toàn bộ
 * phần còn lại của trang, và SVG thì chụp màn hình ở độ phân giải nào cũng nét —
 * đúng thứ cần cho một slide chiếu lên máy chiếu.
 */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, type ThongKe, api, token } from "@/lib/api";
import { NutNgonNgu, useNgonNgu } from "@/components/NgonNguProvider";
import type { Khoa } from "@/lib/i18n";

type Dich = (khoa: Khoa, tham?: Record<string, string | number>) => string;

const KHOA_KIND: Record<string, Khoa> = {
  grounded: "kind.grounded",
  no_answer: "kind.no_answer",
  external: "kind.external",
  cached_external: "kind.cached_external",
  chitchat: "kind.chitchat",
};

/** Loại lạ thì hiện nguyên mã: xấu nhưng trung thực, và lộ ra để bổ sung. */
function nhanKind(t: Dich, kind: string): string {
  return kind in KHOA_KIND ? t(KHOA_KIND[kind]) : kind;
}

const MAU_KIND: Record<string, string> = {
  grounded: "#2563eb",
  no_answer: "#94a3b8",
  external: "#f59e0b",
  cached_external: "#10b981",
  chitchat: "#a78bfa",
};

export default function TrangThongKe() {
  const router = useRouter();
  const [tk, setTk] = useState<ThongKe | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const { t } = useNgonNgu();

  const tai = useCallback(async () => {
    setLoi(null);
    try {
      setTk(await api.thongKe());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        token.xoa();
        router.replace("/");
        return;
      }
      setLoi(t("tk.khongTaiDuoc"));
    }
  }, [router]);

  useEffect(() => {
    if (!token.access()) {
      router.replace("/");
      return;
    }
    void tai();
  }, [router, tai]);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-lg font-semibold tracking-tight">{t("tk.tieuDe")}</h1>
        <div className="flex items-center gap-3">
          <NutNgonNgu />
          <Link href="/notebooks" className="text-sm text-mo underline underline-offset-4">
            ← {t("nb.veDanhSach")}
          </Link>
        </div>
      </header>

      {loi && (
        <div className="mt-6 rounded-lg border border-vien px-5 py-4">
          <p className="text-sm text-canh-bao">{loi}</p>
          <button
            onClick={() => void tai()}
            className="mt-2 rounded-md border border-nhan px-3 py-1.5 text-sm text-nhan"
          >
            {t("chung.thuLai")}
          </button>
        </div>
      )}

      {!tk && !loi && <KhungCho />}

      {tk && (
        <div className="mt-8 space-y-10">
          <section>
            <TieuDe>{t("tk.khoTriThuc")}</TieuDe>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <O nhan={t("tk.notebook")} so={tk.so_notebook} />
              <O nhan={t("tk.taiLieu")} so={tk.so_nguon} />
              <O nhan={t("tk.doanTriThuc")} so={tk.so_chunk} />
              <O nhan={t("tk.dungLuong")} so={dungLuong(tk.dung_luong_bytes)} />
            </div>
          </section>

          <section>
            <TieuDe>{t("tk.loaiCauTraLoi")}</TieuDe>
            <p className="mt-1 text-sm text-mo">
              {t("tk.moTaLoaiCauTraLoi")}
            </p>
            <PhanBo phanBo={tk.phan_bo_answer_kind} t={t} />
          </section>

          <section>
            <TieuDe>{t("tk.doTre")}</TieuDe>
            <p className="mt-1 text-sm text-mo">
              {t("tk.moTaDoTre")}
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <TheDoTre nhan={t("tk.trenMay")} doTre={tk.do_tre_privacy} t={t} />
              <TheDoTre nhan={t("tk.guiRaNgoai")} doTre={tk.do_tre_fast} t={t} />
            </div>
          </section>

          <section>
            <TieuDe>{t("tk.goiNgoai")}</TieuDe>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <O nhan={t("tk.luotGoiThat")} so={tk.so_luot_goi_ngoai} />
              <O nhan={t("tk.luotTuDem")} so={tk.so_luot_tu_cache} />
              <O
                nhan={t("tk.tiLeDungLai")}
                so={`${Math.round(tk.ty_le_cache_hit * 100)}%`}
              />
              <O nhan={t("tk.cauDangLuu")} so={tk.so_ban_ghi_cache} />
            </div>
          </section>

          <section>
            <TieuDe>{t("tk.luotHoi30Ngay")}</TieuDe>
            <BieuDoCot diem={tk.luot_hoi_theo_ngay} t={t} />
          </section>
        </div>
      )}
    </div>
  );
}

function TieuDe({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-semibold uppercase tracking-wider text-mo">{children}</h2>;
}

function O({ nhan, so }: { nhan: string; so: number | string }) {
  return (
    <div className="rounded-lg border border-vien bg-the px-4 py-3">
      <p className="text-2xl font-semibold tabular-nums">{so}</p>
      <p className="mt-0.5 text-xs text-mo">{nhan}</p>
    </div>
  );
}

function TheDoTre({
  nhan,
  doTre,
  t,
}: {
  nhan: string;
  doTre: ThongKe["do_tre_privacy"];
  t: Dich;
}) {
  return (
    <div className="rounded-lg border border-vien bg-the px-4 py-3">
      <p className="text-sm font-medium">{nhan}</p>
      {doTre.so_luot === 0 ? (
        <p className="mt-2 text-sm text-mo">{t("tk.chuaCoLuotNao")}</p>
      ) : (
        <dl className="mt-2 grid grid-cols-3 gap-2 text-sm">
          <div>
            <dt className="text-xs text-mo">{t("tk.trungBinh")}</dt>
            <dd className="tabular-nums">{giay(doTre.trung_binh_ms)}</dd>
          </div>
          <div>
            <dt className="text-xs text-mo">p95</dt>
            <dd className="tabular-nums">{giay(doTre.p95_ms)}</dd>
          </div>
          <div>
            <dt className="text-xs text-mo">{t("tk.soLuot")}</dt>
            <dd className="tabular-nums">{doTre.so_luot}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

/**
 * Thanh xếp chồng cho phân bố `answer_kind` — AC-4 và AC-5.
 *
 * Chọn thanh xếp chồng thay vì hình tròn: mắt so sánh độ dài chính xác hơn hẳn
 * so với so sánh diện tích các múi, và nó cũng đọc được khi bị thu nhỏ trong
 * một slide.
 */
function PhanBo({ phanBo, t }: { phanBo: Record<string, number>; t: Dich }) {
  const muc = Object.entries(phanBo).sort((a, b) => b[1] - a[1]);
  const tong = muc.reduce((s, [, n]) => s + n, 0);

  if (tong === 0) {
    return (
      <p className="mt-3 rounded-lg border border-dashed border-vien px-4 py-6 text-center text-sm text-mo">
        {t("tk.chuaCoCauTraLoi")}
      </p>
    );
  }

  return (
    <div className="mt-3">
      <div className="flex h-7 overflow-hidden rounded-md">
        {muc.map(([kind, n]) => (
          <div
            key={kind}
            style={{ width: `${(n / tong) * 100}%`, background: MAU_KIND[kind] ?? "#64748b" }}
            title={`${nhanKind(t, kind)}: ${n}`}
          />
        ))}
      </div>
      <ul className="mt-3 space-y-1.5">
        {muc.map(([kind, n]) => (
          <li key={kind} className="flex items-center gap-2 text-sm">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: MAU_KIND[kind] ?? "#64748b" }}
            />
            <span className="flex-1">{nhanKind(t, kind)}</span>
            <span className="tabular-nums text-mo">
              {n} · {Math.round((n / tong) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function BieuDoCot({
  diem,
  t,
}: {
  diem: { ngay: string; so_luot: number }[];
  t: Dich;
}) {
  if (diem.length === 0) {
    return (
      <p className="mt-3 rounded-lg border border-dashed border-vien px-4 py-6 text-center text-sm text-mo">
        {t("tk.chuaCoLuotHoi")}
      </p>
    );
  }

  const W = 640;
  const H = 160;
  const dem = 26;
  const dinh = Math.max(...diem.map((d) => d.so_luot));
  const rong = W / diem.length;

  return (
    <div className="mt-3 overflow-x-auto rounded-lg border border-vien bg-the p-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-40 w-full" role="img"
           aria-label={t("tk.bieuDoNhan")}>
        {diem.map((d, i) => {
          const cao = dinh ? ((H - dem) * d.so_luot) / dinh : 0;
          return (
            <rect
              key={d.ngay}
              x={i * rong + rong * 0.15}
              y={H - dem - cao}
              width={rong * 0.7}
              height={cao}
              rx={2}
              fill="#2563eb"
            >
              <title>{t("tk.luotNgay", { ngay: d.ngay, so: d.so_luot })}</title>
            </rect>
          );
        })}
        <line x1={0} y1={H - dem} x2={W} y2={H - dem} stroke="currentColor" opacity={0.25} />
        <text x={0} y={H - 8} fontSize={11} fill="currentColor" opacity={0.6}>
          {diem[0].ngay}
        </text>
        <text x={W} y={H - 8} fontSize={11} textAnchor="end" fill="currentColor" opacity={0.6}>
          {diem[diem.length - 1].ngay}
        </text>
      </svg>
    </div>
  );
}

function KhungCho() {
  // Skeleton thay vì màn hình trắng — US-042 AC-2.
  return (
    <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className="h-20 animate-pulse rounded-lg border border-vien bg-the" />
      ))}
    </div>
  );
}

function dungLuong(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const mb = bytes / 1024 / 1024;
  if (mb < 1) return `${(bytes / 1024).toFixed(0)} KB`;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

function giay(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}
