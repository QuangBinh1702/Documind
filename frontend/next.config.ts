import type { NextConfig } from "next";

/**
 * Không proxy `/api/*` qua Next.js.
 *
 * Cách hiển nhiên là dùng `rewrites()` để trình duyệt chỉ thấy một origin và
 * khỏi lo CORS. Đã thử, và nó **giết chết streaming**: proxy của Next gom cả
 * phản hồi rồi mới trả về một lượt.
 *
 * Đo được trên cùng một câu hỏi:
 *
 *     trực tiếp FastAPI   sự kiện đầu 0.2s · token đầu 26.3s
 *     qua rewrites()      mọi thứ đến cùng lúc ở 27.8s
 *
 * Với một giao diện mà điểm bán là câu trả lời hiện dần và nhãn "đang tìm trong
 * tài liệu" xuất hiện ngay, đó không phải chậm hơn một chút — đó là mất hẳn
 * tính năng. US-012 AC-2 đặt mốc token đầu tiên dưới ba giây, và qua proxy thì
 * mốc đó không thể đạt được dù backend nhanh đến đâu.
 *
 * Nên trình duyệt gọi thẳng FastAPI. Đổi lại phải bật CORS ở backend, và origin
 * của giao diện phải nằm trong `allow_origins` — đó là một dòng cấu hình, rẻ
 * hơn nhiều so với việc mất streaming.
 */
const nextConfig: NextConfig = {};

export default nextConfig;
