"use client";

/**
 * Tuỳ chọn hiển thị cá nhân, lưu ở máy này.
 *
 * Tách khỏi `NgonNguProvider` (đi lên máy chủ theo `users.locale`) và khỏi
 * `NutChuDe` (chủ đề sáng/tối, có khoá riêng vì phải áp trước lúc trang vẽ):
 * đây là những công tắc nhỏ, chỉ ảnh hưởng tới cách nhìn của một người trên một
 * máy, và không đáng để thêm cột vào bảng `users`.
 *
 * Thay đổi phát ra một sự kiện trên `window` chứ không chỉ ghi `localStorage`.
 * Menu Cài đặt và cột hội thoại là hai cây React khác nhau; không có sự kiện
 * này thì bật công tắc xong phải tải lại trang mới thấy tác dụng.
 */

import { useEffect, useState } from "react";

export type TuyChon = {
  /**
   * Hiện tên mô hình cạnh mỗi câu trả lời — US-030 AC-3.
   *
   * **Mặc định tắt.** Với người dùng thường, `gemma4:31b` là một chuỗi không
   * nói lên điều gì và chỉ làm rối chân câu trả lời. Nhưng nó vẫn phải bật được
   * — nhãn mô hình là một tiêu chí nghiệm thu, và lúc trình bày đồ án thì đó
   * đúng là thứ cần chỉ ra.
   */
  hienMoHinh: boolean;
};

const KHOA = "documind.tuychon";
const SU_KIEN = "documind:tuychon";

export const MAC_DINH: TuyChon = { hienMoHinh: false };

export function docTuyChon(): TuyChon {
  if (typeof window === "undefined") return MAC_DINH;
  try {
    return { ...MAC_DINH, ...JSON.parse(localStorage.getItem(KHOA) ?? "{}") };
  } catch {
    return MAC_DINH;
  }
}

export function luuTuyChon(sua: Partial<TuyChon>): TuyChon {
  const moi = { ...docTuyChon(), ...sua };
  try {
    localStorage.setItem(KHOA, JSON.stringify(moi));
  } catch {
    /* chế độ riêng tư của trình duyệt — công tắc chỉ sống trong phiên này */
  }
  window.dispatchEvent(new CustomEvent(SU_KIEN));
  return moi;
}

/**
 * Đọc tuỳ chọn và theo dõi thay đổi.
 *
 * Lượt vẽ đầu tiên luôn trả về mặc định, kể cả khi `localStorage` có giá trị
 * khác: máy chủ không đọc được `localStorage`, nên đọc ngay lúc dựng sẽ làm HTML
 * của máy chủ và của trình duyệt lệch nhau và React báo lỗi hydrate.
 */
export function useTuyChon(): TuyChon {
  const [tuyChon, setTuyChon] = useState<TuyChon>(MAC_DINH);

  useEffect(() => {
    const doc = () => setTuyChon(docTuyChon());
    doc();
    window.addEventListener(SU_KIEN, doc);
    // `storage` bắn khi người dùng đổi công tắc ở một tab khác.
    window.addEventListener("storage", doc);
    return () => {
      window.removeEventListener(SU_KIEN, doc);
      window.removeEventListener("storage", doc);
    };
  }, []);

  return tuyChon;
}
