import type { Metadata } from "next";
import "./globals.css";
import { NgonNguProvider } from "@/components/NgonNguProvider";

/**
 * Siêu dữ liệu trang. Cố ý **không** dịch — Next dựng nó ở máy chủ, trước khi
 * biết người mở trang chọn ngôn ngữ nào. Chuỗi này chỉ xuất hiện ở thẻ mô tả
 * cho công cụ tìm kiếm và ở tiêu đề tab, không phải trong giao diện.
 */
export const metadata: Metadata = {
  title: "DocuMind",
  description: "Hỏi đáp trên tài liệu của bạn, luôn kèm trích dẫn kiểm chứng được",
};

/**
 * Áp chế độ tối TRƯỚC khi trang vẽ lần đầu — US-043 AC-3.
 *
 * Phải là một script chặn đặt trong `<head>`. Làm việc này trong `useEffect`
 * cũng chạy đúng, nhưng React chỉ chạy sau lần vẽ đầu tiên, nên người dùng để
 * chế độ tối sẽ thấy một nháy nền trắng ở mọi lần tải trang.
 *
 * Bọc trong try/catch vì `localStorage` ném lỗi ở chế độ ẩn danh của một số
 * trình duyệt, và một ngoại lệ ở đây làm hỏng cả trang.
 */
const AP_CHU_DE = `
try {
  var c = localStorage.getItem("documind.chu-de");
  if (c === "toi") document.documentElement.dataset.theme = "dark";
  else if (c === "sang") document.documentElement.dataset.theme = "light";
  var n = localStorage.getItem("documind.ngon-ngu");
  if (n === "vi" || n === "en") document.documentElement.lang = n;
} catch (e) {}
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: AP_CHU_DE }} />
      </head>
      <body className="h-full antialiased">
        <NgonNguProvider>
          <a href="#noi-dung" className="skip-link">
            Tới nội dung chính
          </a>
          <div id="noi-dung" className="h-full">
            {children}
          </div>
        </NgonNguProvider>
      </body>
    </html>
  );
}
