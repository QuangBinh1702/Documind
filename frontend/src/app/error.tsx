"use client";

/**
 * Lưới an toàn cho lỗi hiển thị — US-042 AC-3.
 *
 * Không có tệp này thì một ngoại lệ trong lúc vẽ cho ra màn hình mặc định của
 * Next, bằng tiếng Anh, không có nút nào để đi tiếp. Ở đây vẫn giữ nguyên bố
 * cục và ngôn ngữ của ứng dụng, và cho một việc làm được: thử lại.
 */

import { useNgonNgu } from "@/components/NgonNguProvider";

export default function LoiTrang({ reset }: { error: Error; reset: () => void }) {
  const { t } = useNgonNgu();
  return (
    <main className="grid h-full place-items-center px-6 text-center">
      <div>
        <p className="font-medium">{t("loi.trangHong")}</p>
        <button
          onClick={reset}
          className="mt-3 rounded-md border border-nhan px-3 py-1.5 text-sm text-nhan"
        >
          {t("chung.thuLai")}
        </button>
      </div>
    </main>
  );
}
