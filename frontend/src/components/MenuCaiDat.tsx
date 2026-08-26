"use client";

/**
 * Một nút Cài đặt duy nhất cho mọi tuỳ chọn cá nhân — US-036, US-043, US-004.
 *
 * Bản trước rải ngôn ngữ (2 nút), chủ đề (3 nút), đổi mật khẩu, số liệu và
 * đăng xuất thành bảy điều khiển trên thanh tiêu đề của mọi trang. Chúng không
 * liên quan tới việc đang làm — hỏi tài liệu — mà lại đứng ngang hàng với nó,
 * nên thanh tiêu đề lúc nào cũng đông và không có gì nổi bật. Giờ thanh tiêu đề
 * chỉ giữ thứ thuộc về notebook; mọi tuỳ chọn nằm sau một bánh răng.
 *
 * `taiKhoan=false` cho trang chưa đăng nhập và trang xem chia sẻ: vẫn đổi được
 * ngôn ngữ và giao diện, không có phần tài khoản.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, api, token } from "@/lib/api";
import { Bt } from "@/components/BieuTuong";
import { useNgonNgu } from "@/components/NgonNguProvider";
import { type ChuDe, KHOA_CHU_DE, apDung } from "@/components/NutChuDe";
import type { NgonNgu } from "@/lib/i18n";

const MAT_KHAU_TOI_THIEU = 8;

export function MenuCaiDat({
  taiKhoan = true,
  email,
}: {
  taiKhoan?: boolean;
  email?: string;
}) {
  const [mo, setMo] = useState(false);
  const [chuDe, setChuDe] = useState<ChuDe>("he-thong");
  const [doiMatKhau, setDoiMatKhau] = useState(false);
  const router = useRouter();
  const { ngonNgu, doi, t } = useNgonNgu();
  const khung = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const luu = localStorage.getItem(KHOA_CHU_DE) as ChuDe | null;
      if (luu === "sang" || luu === "toi" || luu === "he-thong") setChuDe(luu);
    } catch {
      /* dùng mặc định */
    }
  }, []);

  // Esc đóng; bấm ra ngoài đóng.
  useEffect(() => {
    if (!mo) return;
    function phim(e: KeyboardEvent) {
      if (e.key === "Escape") setMo(false);
    }
    function chuot(e: MouseEvent) {
      if (khung.current && !khung.current.contains(e.target as Node)) setMo(false);
    }
    window.addEventListener("keydown", phim);
    window.addEventListener("mousedown", chuot);
    return () => {
      window.removeEventListener("keydown", phim);
      window.removeEventListener("mousedown", chuot);
    };
  }, [mo]);

  function doiChuDe(moi: ChuDe) {
    setChuDe(moi);
    apDung(moi);
    try {
      localStorage.setItem(KHOA_CHU_DE, moi);
    } catch {
      /* chỉ sống trong phiên này */
    }
  }

  return (
    <div ref={khung} className="relative">
      <button
        onClick={() => setMo((m) => !m)}
        aria-expanded={mo}
        aria-haspopup="menu"
        title={t("caiDat.tieuDe")}
        className="nut-icon"
      >
        <Bt.caiDat size={18} />
        <span className="sr-only">{t("caiDat.tieuDe")}</span>
      </button>

      {mo && (
        <div
          role="menu"
          className="menu-noi absolute right-0 z-30 mt-2 w-72 origin-top-right"
        >
          {taiKhoan && email && (
            <div className="border-b border-vien px-4 py-3">
              <p className="text-[11px] uppercase tracking-wider text-mo">{t("caiDat.taiKhoan")}</p>
              <p className="mt-0.5 truncate text-sm font-medium" title={email}>
                {email}
              </p>
            </div>
          )}

          <Muc nhan={t("gd.ngonNgu")}>
            <NhomLuaChon<NgonNgu>
              giaTri={ngonNgu}
              onDoi={doi}
              muc={[
                ["vi", "Tiếng Việt"],
                ["en", "English"],
              ]}
            />
          </Muc>

          <Muc nhan={t("gd.cheDoHienThi")}>
            <NhomLuaChon<ChuDe>
              giaTri={chuDe}
              onDoi={doiChuDe}
              muc={[
                ["sang", t("gd.sang"), <Bt.matTroi key="s" size={14} />],
                ["toi", t("gd.toi"), <Bt.trang key="t" size={14} />],
                ["he-thong", t("gd.theoMay"), <Bt.manHinh key="m" size={14} />],
              ]}
            />
          </Muc>

          {taiKhoan && (
            <div className="border-t border-vien py-1.5">
              <Link href="/thong-ke" role="menuitem" className="muc-menu" onClick={() => setMo(false)}>
                <Bt.thongKe /> {t("nb.soLieu")}
              </Link>
              <button
                role="menuitem"
                className="muc-menu w-full"
                aria-expanded={doiMatKhau}
                onClick={() => setDoiMatKhau((d) => !d)}
              >
                <Bt.khoa /> {t("tk.doiMatKhau")}
                <Bt.mui className={`ml-auto transition-transform ${doiMatKhau ? "rotate-180" : ""}`} />
              </button>
              {doiMatKhau && <FormDoiMatKhau onXong={() => setDoiMatKhau(false)} />}
              <button
                role="menuitem"
                className="muc-menu w-full text-canh-bao"
                onClick={async () => {
                  await api.dangXuat();
                  router.replace("/");
                }}
              >
                <Bt.ra /> {t("auth.dangXuat")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Muc({ nhan, children }: { nhan: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-3">
      <p className="mb-1.5 text-[11px] uppercase tracking-wider text-mo">{nhan}</p>
      {children}
    </div>
  );
}

function NhomLuaChon<T extends string>({
  giaTri,
  onDoi,
  muc,
}: {
  giaTri: T;
  onDoi: (v: T) => void;
  muc: [T, string, React.ReactNode?][];
}) {
  return (
    <div role="radiogroup" className="grid gap-1" style={{ gridTemplateColumns: `repeat(${muc.length}, 1fr)` }}>
      {muc.map(([ma, nhan, icon]) => (
        <button
          key={ma}
          role="radio"
          aria-checked={giaTri === ma}
          onClick={() => onDoi(ma)}
          className={`flex items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 text-xs transition-colors ${
            giaTri === ma
              ? "border-nhan bg-nhan/10 font-medium text-nhan"
              : "border-vien text-mo hover:border-mo hover:text-chu"
          }`}
        >
          {icon}
          {nhan}
        </button>
      ))}
    </div>
  );
}

/** Đổi mật khẩu ngay trong menu — không mở modal cho một việc ba ô nhập. */
function FormDoiMatKhau({ onXong }: { onXong: () => void }) {
  const [cu, setCu] = useState("");
  const [moi, setMoi] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [xong, setXong] = useState(false);
  const [dangGui, setDangGui] = useState(false);
  const { t } = useNgonNgu();
  const guiDuoc = cu.length > 0 && moi.length >= MAT_KHAU_TOI_THIEU && !dangGui;

  async function gui(e: React.FormEvent) {
    e.preventDefault();
    if (!guiDuoc) return;
    setLoi(null);
    setDangGui(true);
    try {
      token.luu(await api.doiMatKhau(cu, moi));
      setXong(true);
      setTimeout(onXong, 1800);
    } catch (err) {
      setLoi(err instanceof ApiError ? err.message : t("auth.khongKetNoi"));
    } finally {
      setDangGui(false);
    }
  }

  if (xong) return <p className="px-4 py-2 text-xs text-nhan">{t("tk.daDoiMatKhau")}</p>;

  return (
    <form onSubmit={gui} className="space-y-2 px-4 pb-3 pt-1">
      <input
        type="password"
        autoComplete="current-password"
        value={cu}
        onChange={(e) => setCu(e.target.value)}
        placeholder={t("tk.matKhauCu")}
        className="o-nhap-nho"
      />
      <input
        type="password"
        autoComplete="new-password"
        value={moi}
        onChange={(e) => setMoi(e.target.value)}
        placeholder={`${t("tk.matKhauMoi")} · ${t("auth.matKhauGoiY")}`}
        className="o-nhap-nho"
      />
      {loi && <p className="text-xs text-canh-bao">{loi}</p>}
      <button type="submit" disabled={!guiDuoc} className="nut-chinh w-full py-1.5 text-xs">
        {dangGui ? "…" : t("tk.luu")}
      </button>
    </form>
  );
}
