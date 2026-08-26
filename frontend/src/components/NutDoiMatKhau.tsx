"use client";

/**
 * Đổi mật khẩu — US-004 AC-2, AC-3.
 *
 * Máy chủ cấp cặp token mới sau khi đổi (để phiên đang dùng không bị đá ra),
 * và mọi token cũ — kể cả trên máy khác — chết theo vì chúng mang dấu vân tay
 * của mật khẩu cũ. Lưu cặp mới ngay là bắt buộc, không thì chính phiên này
 * cũng bị đăng xuất ở request kế tiếp.
 */

import { useState } from "react";
import { ApiError, api, token } from "@/lib/api";
import { useNgonNgu } from "@/components/NgonNguProvider";

const MAT_KHAU_TOI_THIEU = 8;

export function NutDoiMatKhau() {
  const [mo, setMo] = useState(false);
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
      setCu("");
      setMoi("");
    } catch (err) {
      setLoi(err instanceof ApiError ? err.message : t("auth.khongKetNoi"));
    } finally {
      setDangGui(false);
    }
  }

  function dong() {
    setMo(false);
    setLoi(null);
    setXong(false);
  }

  return (
    <div className="relative">
      <button onClick={() => (mo ? dong() : setMo(true))} className="underline underline-offset-4">
        {t("tk.doiMatKhau")}
      </button>

      {mo && (
        <>
          <div className="fixed inset-0 z-10" onClick={dong} />
          <form
            onSubmit={gui}
            className="absolute right-0 z-20 mt-2 w-72 rounded-lg border border-vien bg-the p-4 text-left shadow-lg"
          >
            <p className="text-sm font-medium text-chu">{t("tk.doiMatKhau")}</p>

            {xong ? (
              <p className="mt-2 text-xs text-nhan">{t("tk.daDoiMatKhau")}</p>
            ) : (
              <>
                <label className="mt-3 block text-xs">
                  <span className="mb-1 block text-mo">{t("tk.matKhauCu")}</span>
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={cu}
                    onChange={(e) => setCu(e.target.value)}
                    className="w-full rounded-md border border-vien bg-nen px-2 py-1.5 text-sm text-chu outline-none focus:border-nhan"
                  />
                </label>
                <label className="mt-2 block text-xs">
                  <span className="mb-1 block text-mo">{t("tk.matKhauMoi")}</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={moi}
                    onChange={(e) => setMoi(e.target.value)}
                    placeholder={t("auth.matKhauGoiY")}
                    className="w-full rounded-md border border-vien bg-nen px-2 py-1.5 text-sm text-chu outline-none focus:border-nhan"
                  />
                </label>
                {loi && <p className="mt-2 text-xs text-canh-bao">{loi}</p>}
                <div className="mt-3 flex gap-2">
                  <button
                    type="submit"
                    disabled={!guiDuoc}
                    className="rounded-md bg-nhan px-3 py-1.5 text-xs font-medium text-nen disabled:opacity-45"
                  >
                    {dangGui ? "…" : t("tk.luu")}
                  </button>
                  <button
                    type="button"
                    onClick={dong}
                    className="rounded-md border border-vien px-3 py-1.5 text-xs text-mo"
                  >
                    {t("chung.huy")}
                  </button>
                </div>
              </>
            )}
          </form>
        </>
      )}
    </div>
  );
}
