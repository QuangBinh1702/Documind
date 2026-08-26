"use client";

/**
 * Danh sách notebook — US-005 AC-1, AC-2.
 *
 * Chưa đăng nhập mà vào thẳng URL này thì bị đẩy về trang đăng nhập (AC-4 của
 * US-003). Kiểm ở client là để trải nghiệm mượt; quyền thật vẫn do máy chủ giữ,
 * và nó trả 401 bất kể client nghĩ gì.
 */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, type Notebook, api, token } from "@/lib/api";
import { MenuCaiDat } from "@/components/MenuCaiDat";
import { useNgonNgu } from "@/components/NgonNguProvider";
import type { Khoa } from "@/lib/i18n";

export default function TrangNotebook() {
  const router = useRouter();
  const [ds, setDs] = useState<Notebook[] | null>(null);
  const [email, setEmail] = useState("");
  const [tieuDe, setTieuDe] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const { t } = useNgonNgu();

  const tai = useCallback(async () => {
    try {
      const [me, list] = await Promise.all([api.toiLaAi(), api.danhSachNotebook()]);
      setEmail(me.email);
      setDs(list);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        token.xoa();
        router.replace("/");
        return;
      }
      setLoi(t("nb.khongTaiDuoc"));
      setDs([]);
    }
  }, [router]);

  useEffect(() => {
    if (!token.access()) {
      router.replace("/");
      return;
    }
    void tai();
  }, [router, tai]);

  async function tao(e: React.FormEvent) {
    e.preventDefault();
    // Không đặt tên biến này là `t`: nó sẽ che mất hàm dịch cùng tên.
    const ten = tieuDe.trim();
    if (!ten) return;
    try {
      const nb = await api.taoNotebook(ten);
      setTieuDe("");
      // AC-2: mở ra ngay, không bắt bấm thêm một lần nữa.
      router.push(`/notebooks/${nb.id}`);
    } catch {
      setLoi(t("nb.khongTaoDuoc"));
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <header className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-tight text-nhan">DocuMind</p>
          <h1 className="mt-1 text-[22px] font-semibold tracking-tight">{t("nb.cuaBan")}</h1>
        </div>
        <MenuCaiDat email={email} />
      </header>

      <form onSubmit={tao} className="o-nhap mt-7 flex items-center gap-2 pr-1.5">
        <input
          value={tieuDe}
          onChange={(e) => setTieuDe(e.target.value)}
          placeholder={t("nb.tenMoi")}
          className="flex-1 bg-transparent px-4 py-2.5 text-[15px] outline-none placeholder:text-mo/70"
        />
        <button type="submit" disabled={!tieuDe.trim()} className="nut-chinh py-1.5">
          {t("nb.tao")}
        </button>
      </form>

      {/* Lỗi phải kèm một việc làm được, không chỉ là một câu buồn — US-042 AC-3. */}
      {loi && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-canh-bao bg-canh-bao-nen px-4 py-3">
          <p className="text-sm text-canh-bao">{loi}</p>
          <button
            onClick={() => {
              setLoi(null);
              setDs(null);
              void tai();
            }}
            className="rounded-md border border-canh-bao px-2.5 py-1 text-xs text-canh-bao"
          >
            {t("chung.thuLai")}
          </button>
        </div>
      )}

      <div className="mt-8">
        {ds === null ? (
          // Khung xương thay cho màn hình trắng — AC-2. Nó cũng cho biết trước
          // trang sắp có hình dạng thế nào, nên lúc dữ liệu về không bị nhảy.
          <ul className="divide-y divide-vien rounded-lg border border-vien bg-the">
            {Array.from({ length: 3 }, (_, i) => (
              <li key={i} className="flex items-center justify-between px-5 py-5">
                <span className="h-4 w-48 animate-pulse rounded bg-vien" />
                <span className="h-3 w-24 animate-pulse rounded bg-vien" />
              </li>
            ))}
          </ul>
        ) : ds.length === 0 ? (
          // Trạng thái rỗng phải hướng dẫn, không phải khoảng trắng — US-042 AC-1.
          <div className="rounded-lg border border-dashed border-vien px-5 py-12 text-center">
            <ThuMucRong />
            <p className="mt-4 font-medium">{t("nb.chuaCo")}</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-mo">
              {t("nb.chuaCoMoTa")}
            </p>
          </div>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {ds.map((nb) => (
              <li key={nb.id}>
                <Link
                  href={`/notebooks/${nb.id}`}
                  className="group flex h-full flex-col rounded-xl border border-vien bg-the px-5 py-4 transition-[border-color,box-shadow] hover:border-nhan hover:shadow-[0_2px_12px_rgba(0,0,0,0.05)]"
                >
                  <span className="text-[15px] font-semibold tracking-tight group-hover:text-nhan">
                    {nb.title}
                  </span>
                  <span className="mt-2 text-sm text-mo">
                    {nb.source_count === 0
                      ? t("nb.chuaCoTaiLieu")
                      : nb.ready_count === nb.source_count
                        ? t("nb.soTaiLieu", { so: nb.source_count })
                        : t("nb.daXuLy", {
                            xong: nb.ready_count,
                            tong: nb.source_count,
                          })}
                  </span>
                  <span className="mt-auto pt-3 text-[11px] text-mo/70">
                    {t("nb.capNhat", { luc: thoiGianTuongDoi(nb.updated_at, t) })}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** "5 phút trước", "hôm qua"… — đủ thô để không phải cập nhật từng giây. */
function thoiGianTuongDoi(
  iso: string,
  t: (khoa: Khoa, tham?: Record<string, string | number>) => string,
): string {
  const giay = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (giay < 60) return t("tg.vuaXong");
  if (giay < 3600) return t("tg.phutTruoc", { so: Math.floor(giay / 60) });
  if (giay < 86400) return t("tg.gioTruoc", { so: Math.floor(giay / 3600) });
  if (giay < 86400 * 30) return t("tg.ngayTruoc", { so: Math.floor(giay / 86400) });
  return new Date(iso).toLocaleDateString();
}

/** Minh hoạ cho trạng thái rỗng. SVG viết tay — một hình đơn giản không đáng
 *  kéo theo cả một bộ icon, và nó ăn theo màu chữ nên tự đúng ở chế độ tối. */
function ThuMucRong() {
  return (
    <svg
      viewBox="0 0 96 72"
      className="mx-auto h-16 w-auto text-mo"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinejoin="round"
      aria-hidden="true"
      opacity={0.55}
    >
      <path d="M6 18a6 6 0 0 1 6-6h22l7 8h37a6 6 0 0 1 6 6v34a6 6 0 0 1-6 6H12a6 6 0 0 1-6-6z" />
      <path d="M30 40h36M30 50h24" strokeLinecap="round" opacity={0.6} />
    </svg>
  );
}
