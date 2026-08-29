"use client";

/**
 * Chia sẻ một đoạn hội thoại chỉ đọc — US-039, quyết định 0004.
 *
 * Ba điều phải nói thẳng ra trong hộp này, vì cả ba đều là bất ngờ khó chịu nếu
 * người dùng chỉ phát hiện ra sau khi đã gửi liên kết đi:
 *
 * 1. **Chia sẻ đúng đoạn hội thoại đang mở**, không phải cả notebook. Những
 *    hội thoại khác vẫn riêng tư.
 * 2. **Ai có liên kết đều đọc được**, kể cả người chưa đăng nhập, và họ đọc
 *    được cả tài liệu nguồn chứ không chỉ những đoạn đã trích.
 * 3. **Muốn hỏi thêm thì người xem phải đăng nhập**, và câu hỏi của họ vào lịch
 *    sử của chính họ.
 */

import { useEffect, useState } from "react";
import { type LienKetChiaSe, api } from "@/lib/api";
import { Bt } from "@/components/BieuTuong";
import { useNgonNgu } from "@/components/NgonNguProvider";

export function NutChiaSe({ nbId, phienId }: { nbId: string; phienId: string | null }) {
  const [mo, setMo] = useState(false);
  const [lienKet, setLienKet] = useState<LienKetChiaSe | null>(null);
  const [dangLam, setDangLam] = useState(false);
  const [daChep, setDaChep] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const { t } = useNgonNgu();

  useEffect(() => {
    if (!mo) return;
    setLienKet(null);
    api
      .lienKetChiaSe(nbId, phienId)
      .then(setLienKet)
      .catch(() => setLienKet(null));
  }, [mo, nbId, phienId]);

  const url = lienKet ? `${window.location.origin}${lienKet.duong_dan}` : "";

  async function tao() {
    setDangLam(true);
    setLoi(null);
    try {
      setLienKet(await api.taoLienKetChiaSe(nbId, phienId));
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
      await api.thuHoiLienKetChiaSe(nbId, phienId);
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
        className="nut-phu h-8 gap-1.5"
        title={t("chiaSe.tieuDe")}
      >
        <Bt.chiaSe size={14} />
        {t("chiaSe.nut")}
      </button>

      {mo && (
        <>
          {/* Bấm ra ngoài thì đóng — không có nó thì hộp dính lại trên màn hình. */}
          <div className="fixed inset-0 z-10" onClick={() => setMo(false)} />
          <div className="menu-noi absolute right-0 z-20 mt-2 w-80 p-4">
            <p className="text-sm font-medium">{t("chiaSe.tieuDe")}</p>
            {loi && <p className="mt-2 text-xs text-canh-bao">{loi}</p>}

            {/* Chưa hỏi câu nào thì chưa có hội thoại để chia sẻ. Nói ra, thay
                vì lặng lẽ cấp một liên kết mở ra màn hình trống — đó đúng là
                lỗi mà quyết định 0004 sinh ra để sửa. */}
            {phienId === null ? (
              <p className="mt-1 text-xs text-mo">{t("chiaSe.chuaCoHoiThoai")}</p>
            ) : lienKet ? (
              <>
                <p className="mt-1 text-xs text-mo">{t("chiaSe.daCoMoTa")}</p>
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
                  {t("chiaSe.muonHoiPhaiDangNhap")}
                </p>
              </>
            ) : (
              <>
                <p className="mt-1 text-xs text-mo">{t("chiaSe.chuaCoMoTa")}</p>
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
