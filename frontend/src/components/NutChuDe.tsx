"use client";

/**
 * Chuyển sáng / tối / theo hệ thống — US-043.
 *
 * Ba lựa chọn chứ không phải công tắc hai nấc. "Theo hệ thống" là mặc định và
 * là thứ đúng cho phần lớn người dùng: máy đã tự đổi theo giờ trong ngày rồi.
 * Một công tắc hai nấc buộc người ta phải chọn cứng một bên và mất hành vi đó.
 *
 * Lựa chọn ghi ở `localStorage` (AC-3) và được áp **trước khi trang vẽ** bởi
 * đoạn script nội tuyến trong `layout.tsx`. Nếu đợi React chạy xong mới áp thì
 * mỗi lần tải trang sẽ loé lên nền sáng rồi mới tối lại.
 */

import { useEffect, useState } from "react";

export type ChuDe = "sang" | "toi" | "he-thong";

export const KHOA_CHU_DE = "documind.chu-de";

const NHAN: Record<ChuDe, string> = {
  sang: "Sáng",
  toi: "Tối",
  "he-thong": "Theo máy",
};

export function apDung(chuDe: ChuDe) {
  const goc = document.documentElement;
  if (chuDe === "he-thong") {
    delete goc.dataset.theme;
  } else {
    goc.dataset.theme = chuDe === "toi" ? "dark" : "light";
  }
}

export function NutChuDe() {
  const [chuDe, setChuDe] = useState<ChuDe>("he-thong");

  useEffect(() => {
    try {
      const luu = localStorage.getItem(KHOA_CHU_DE) as ChuDe | null;
      if (luu && luu in NHAN) setChuDe(luu);
    } catch {
      /* trình duyệt chặn localStorage — dùng mặc định, không cần báo gì */
    }
  }, []);

  function doi(moi: ChuDe) {
    setChuDe(moi);
    apDung(moi);
    try {
      localStorage.setItem(KHOA_CHU_DE, moi);
    } catch {
      /* không lưu được thì lựa chọn chỉ sống trong phiên này */
    }
  }

  return (
    <div
      role="group"
      aria-label="Chế độ hiển thị"
      className="flex items-center gap-0.5 rounded-md border border-vien p-0.5"
    >
      {(Object.keys(NHAN) as ChuDe[]).map((k) => (
        <button
          key={k}
          onClick={() => doi(k)}
          aria-pressed={chuDe === k}
          className={`rounded px-1.5 py-0.5 text-[11px] ${
            chuDe === k ? "bg-nhan text-nen" : "text-mo hover:text-chu"
          }`}
        >
          {NHAN[k]}
        </button>
      ))}
    </div>
  );
}
