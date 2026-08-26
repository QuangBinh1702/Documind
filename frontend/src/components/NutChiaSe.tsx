"use client";

/**
 * Chia sẻ notebook chỉ đọc — US-039.
 *
 * Hai điều phải nói thẳng ra trong hộp này, vì cả hai đều là bất ngờ khó chịu
 * nếu người dùng chỉ phát hiện ra sau:
 *
 * 1. **Ai có liên kết đều xem được**, kể cả người chưa đăng nhập. Đó là điều
 *    làm cho liên kết hữu ích, và cũng là rủi ro của nó.
 * 2. **Lượt hỏi của người xem tính vào hạn mức của bạn.** Không có cách nào
 *    khác — người xem không có tài khoản để tính vào.
 */

import { useEffect, useState } from "react";
import { type LienKetChiaSe, api } from "@/lib/api";
import { useNgonNgu } from "@/components/NgonNguProvider";

export function NutChiaSe({ nbId }: { nbId: string }) {
  const [mo, setMo] = useState(false);
  const [lienKet, setLienKet] = useState<LienKetChiaSe | null>(null);
  const [dangLam, setDangLam] = useState(false);
  const [daChep, setDaChep] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const { t } = useNgonNgu();

  useEffect(() => {
    if (!mo) return;
    api
      .lienKetChiaSe(nbId)
      .then(setLienKet)
      .catch(() => setLienKet(null));
  }, [mo, nbId]);

  const url = lienKet ? `${window.location.origin}${lienKet.duong_dan}` : "";

  async function tao() {
    setDangLam(true);
    setLoi(null);
    try {
      setLienKet(await api.taoLienKetChiaSe(nbId));
    } catch {
      setLoi(t("loi.khongLuuDuoc"));
    } finally {
      setDangLam(false);
    }
  }

  async function thuHoi() {
    setDangLam(true);
    setLoi(null);
    try {
      await api.thuHoiLienKetChiaSe(nbId);
      setLienKet(null);
    } catch {
      setLoi(t("loi.khongLuuDuoc"));
    } finally {
      setDangLam(false);
    }
  }

  async function chep() {
    try {
      await navigator.clipboard.writeText(url);
      setDaChep(true);
      setTimeout(() => setDaChep(false), 2000);
    } catch {
      /* trình duyệt chặn clipboard — người dùng vẫn chọn tay được từ ô bên dưới */
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setMo((m) => !m)}
        aria-expanded={mo}
        className="rounded-md border border-vien px-2 py-0.5 text-xs text-mo hover:border-nhan hover:text-nhan"
      >
        {t("chiaSe.nut")}
      </button>

      {mo && (
        <>
          {/* Bấm ra ngoài thì đóng — không có nó thì hộp dính lại trên màn hình. */}
          <div className="fixed inset-0 z-10" onClick={() => setMo(false)} />
          <div className="absolute right-0 z-20 mt-2 w-80 rounded-lg border border-vien bg-the p-4 shadow-lg">
            <p className="text-sm font-medium">{t("chiaSe.tieuDe")}</p>
            {loi && <p className="mt-2 text-xs text-canh-bao">{loi}</p>}

            {lienKet ? (
              <>
                <p className="mt-1 text-xs text-mo">
                  {t("chiaSe.daCoMoTa")}
                </p>
                <input
                  readOnly
                  value={url}
                  onFocus={(e) => e.currentTarget.select()}
                  className="mt-3 w-full rounded-md border border-vien bg-nen px-2 py-1.5 text-xs"
                />
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => void chep()}
                    className="rounded-md bg-nhan px-3 py-1.5 text-xs font-medium text-nen"
                  >
                    {daChep ? t("chiaSe.daChep") : t("chiaSe.chep")}
                  </button>
                  <button
                    onClick={() => void thuHoi()}
                    disabled={dangLam}
                    className="rounded-md border border-vien px-3 py-1.5 text-xs text-mo hover:border-canh-bao hover:text-canh-bao disabled:opacity-45"
                  >
                    {t("chiaSe.thuHoi")}
                  </button>
                </div>
                <p className="mt-3 border-t border-vien pt-2 text-xs text-mo">
                  {t("chiaSe.hanMuc")}
                </p>
              </>
            ) : (
              <>
                <p className="mt-1 text-xs text-mo">
                  {t("chiaSe.chuaCoMoTa")}
                </p>
                <button
                  onClick={() => void tao()}
                  disabled={dangLam}
                  className="mt-3 rounded-md bg-nhan px-3 py-1.5 text-xs font-medium text-nen disabled:opacity-45"
                >
                  {dangLam ? "…" : t("chiaSe.tao")}
                </button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
