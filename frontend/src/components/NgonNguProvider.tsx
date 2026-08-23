"use client";

/**
 * Ngôn ngữ giao diện, dùng chung cho cả cây component — US-036.
 *
 * Lựa chọn nằm ở hai chỗ, và cả hai đều cần:
 *
 * * `localStorage` — đọc được **ngay** khi trang vẽ lần đầu, kể cả trước khi
 *   biết người dùng là ai. Không có nó thì mỗi lần tải trang sẽ hiện tiếng Việt
 *   một nhịp rồi mới đổi sang tiếng Anh.
 * * `users.locale` — theo tài khoản, nên đăng nhập ở máy khác vẫn đúng (AC-2).
 *
 * Khi hai chỗ lệch nhau thì máy chủ thắng: nó là thứ theo người, còn
 * `localStorage` chỉ theo máy.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { type Khoa, type NgonNgu, dich } from "@/lib/i18n";
import { api, token } from "@/lib/api";

const KHOA_LUU = "documind.ngon-ngu";

type BoiCanh = {
  ngonNgu: NgonNgu;
  doi: (n: NgonNgu) => void;
  t: (khoa: Khoa, tham?: Record<string, string | number>) => string;
};

const Ctx = createContext<BoiCanh>({
  ngonNgu: "vi",
  doi: () => {},
  t: (khoa, tham) => dich("vi", khoa, tham),
});

export function NgonNguProvider({ children }: { children: React.ReactNode }) {
  const [ngonNgu, setNgonNgu] = useState<NgonNgu>("vi");

  useEffect(() => {
    try {
      const luu = localStorage.getItem(KHOA_LUU);
      if (luu === "vi" || luu === "en") setNgonNgu(luu);
    } catch {
      /* trình duyệt chặn localStorage — dùng mặc định */
    }

    // Máy chủ là nguồn theo người, nên nó ghi đè bản lưu theo máy.
    if (token.access()) {
      api
        .toiLaAi()
        .then((me) => {
          if (me.locale === "vi" || me.locale === "en") {
            setNgonNgu(me.locale);
            try {
              localStorage.setItem(KHOA_LUU, me.locale);
            } catch {
              /* không lưu được cũng không sao, đã có bản trên máy chủ */
            }
          }
        })
        .catch(() => {
          /* chưa đăng nhập hoặc token hỏng — giữ lựa chọn cục bộ */
        });
    }
  }, []);

  const doi = useCallback((moi: NgonNgu) => {
    setNgonNgu(moi);
    document.documentElement.lang = moi;
    try {
      localStorage.setItem(KHOA_LUU, moi);
    } catch {
      /* bỏ qua */
    }
    if (token.access()) {
      // Không chờ: giao diện phải đổi ngay (AC-1). Lượt ghi này chỉ để lần đăng
      // nhập sau ở máy khác cũng đúng.
      void api.doiNgonNgu(moi).catch(() => {});
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = ngonNgu;
  }, [ngonNgu]);

  const gia_tri = useMemo<BoiCanh>(
    () => ({
      ngonNgu,
      doi,
      t: (khoa, tham) => dich(ngonNgu, khoa, tham),
    }),
    [ngonNgu, doi],
  );

  return <Ctx.Provider value={gia_tri}>{children}</Ctx.Provider>;
}

export function useNgonNgu(): BoiCanh {
  return useContext(Ctx);
}

/** Nút đổi ngôn ngữ. Đặt cạnh nút chế độ tối vì cùng nhóm "tuỳ chọn hiển thị". */
export function NutNgonNgu() {
  const { ngonNgu, doi, t } = useNgonNgu();
  return (
    <div
      role="group"
      aria-label={t("gd.ngonNgu")}
      className="flex items-center gap-0.5 rounded-md border border-vien p-0.5"
    >
      {(["vi", "en"] as const).map((n) => (
        <button
          key={n}
          onClick={() => doi(n)}
          aria-pressed={ngonNgu === n}
          className={`rounded px-1.5 py-0.5 text-[11px] uppercase ${
            ngonNgu === n ? "bg-nhan text-nen" : "text-mo hover:text-chu"
          }`}
        >
          {n}
        </button>
      ))}
    </div>
  );
}
