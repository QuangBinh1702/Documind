"use client";

/**
 * Banner "mất kết nối tới máy chủ" — US-042 AC-4.
 *
 * `navigator.onLine` một mình là không đủ, và đó là cả vấn đề: nó chỉ nói máy
 * có card mạng đang hoạt động hay không. Wi-Fi vẫn nối nhưng máy chủ đã tắt thì
 * `onLine` vẫn `true`, và người dùng ngồi nhìn những nút bấm không phản hồi mà
 * không hiểu vì sao.
 *
 * Nên khi mất kết nối thì hỏi thẳng `/api/health`, và tự thử lại theo nhịp giãn
 * dần cho tới khi máy chủ trả lời. Không giãn dần thì một máy chủ đang chết
 * nhận thêm một request mỗi giây từ mọi tab đang mở.
 */

import { useEffect, useState } from "react";
import { GOC_API } from "@/lib/api";
import { useNgonNgu } from "@/components/NgonNguProvider";

const NHIP_DAU_MS = 2000;
const NHIP_TOI_DA_MS = 30_000;

export function MatKetNoi() {
  const [mat, setMat] = useState(false);
  const { t } = useNgonNgu();

  useEffect(() => {
    let dung = false;
    let hen: ReturnType<typeof setTimeout> | null = null;
    let nhip = NHIP_DAU_MS;

    async function song(): Promise<boolean> {
      try {
        const r = await fetch(`${GOC_API}/api/health`, { cache: "no-store" });
        return r.ok;
      } catch {
        return false;
      }
    }

    async function kiem() {
      if (dung) return;
      const ok = await song();
      if (dung) return;

      setMat(!ok);
      if (ok) {
        nhip = NHIP_DAU_MS;
        return;
      }
      nhip = Math.min(nhip * 2, NHIP_TOI_DA_MS);
      hen = setTimeout(() => void kiem(), nhip);
    }

    function mang_tat() {
      setMat(true);
      void kiem();
    }
    function mang_lai() {
      nhip = NHIP_DAU_MS;
      void kiem();
    }

    window.addEventListener("offline", mang_tat);
    window.addEventListener("online", mang_lai);
    if (typeof navigator !== "undefined" && !navigator.onLine) mang_tat();

    return () => {
      dung = true;
      if (hen) clearTimeout(hen);
      window.removeEventListener("offline", mang_tat);
      window.removeEventListener("online", mang_lai);
    };
  }, []);

  if (!mat) return null;

  return (
    <div
      role="alert"
      className="shrink-0 border-b border-canh-bao bg-canh-bao-nen px-5 py-2 text-sm text-canh-bao"
    >
      {t("chung.matKetNoi")}
    </div>
  );
}
