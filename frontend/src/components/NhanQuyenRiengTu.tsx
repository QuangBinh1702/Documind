"use client";

/**
 * Nhãn cho biết dữ liệu có rời khỏi máy hay không — US-030, US-032.
 *
 * Đây là **thuộc tính của không gian làm việc**, không phải của từng câu trả
 * lời. Bản đầu tiên chen một dòng cảnh báo vào giữa mỗi lượt hội thoại, kèm
 * định danh nội bộ `ollama-cloud:gemma4:31b` và chữ "Privacy Mode" — cả hai đều
 * là ngôn ngữ của người viết mã. Người dùng phải đọc chúng ở mọi câu trả lời mà
 * không làm gì được với chúng.
 *
 * Nay nó là một nhãn nhỏ ở thanh tiêu đề: luôn nhìn thấy nếu muốn tìm, không
 * chen ngang nếu không. Ai cần chi tiết thì rê chuột lên.
 *
 * Không nêu tên mô hình. Tên đó vẫn được ghi đầy đủ ở log máy chủ, ở cột
 * `model_used` của từng tin nhắn, và ở siêu dữ liệu của mỗi lượt chạy đánh giá —
 * những nơi nó thật sự có ích.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function NhanQuyenRiengTu() {
  const [roiKhoiMay, setRoiKhoiMay] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .cauHinh()
      .then((c) => setRoiKhoiMay(c.du_lieu_roi_khoi_may))
      .catch(() => setRoiKhoiMay(null));
  }, []);

  if (roiKhoiMay === null) return null;

  return roiKhoiMay ? (
    <span
      title="Câu hỏi và những đoạn tài liệu liên quan được gửi tới một dịch vụ xử lý bên ngoài. Muốn mọi thứ ở lại máy này thì đổi cấu hình sang chế độ riêng tư."
      className="rounded-full border border-canh-bao px-2 py-0.5 text-[11px] text-canh-bao"
    >
      Xử lý bên ngoài
    </span>
  ) : (
    <span
      title="Toàn bộ xử lý diễn ra trên máy này. Không có nội dung nào được gửi đi đâu cả."
      className="rounded-full border border-vien px-2 py-0.5 text-[11px] text-mo"
    >
      Xử lý trên máy này
    </span>
  );
}
