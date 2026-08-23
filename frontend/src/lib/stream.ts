/**
 * Đọc luồng SSE của endpoint hỏi đáp — hợp đồng ở `SPEC-v1.md` §7.1.
 *
 * Dùng `fetch` + `ReadableStream` chứ không dùng `EventSource`: `EventSource`
 * chỉ gửi được `GET` và không đính kèm header được, mà ở đây cần `POST` với
 * thân JSON và một `Authorization: Bearer`.
 *
 * Phần dễ sai nhất là **ranh giới gói tin**. Một sự kiện SSE kết thúc bằng dòng
 * trống, nhưng mạng cắt dữ liệu ở đâu là chuyện của mạng: một lần đọc có thể
 * trả về hai sự kiện rưỡi. Nửa sự kiện còn lại phải giữ trong bộ đệm chờ lần
 * đọc sau, nếu không thì thỉnh thoảng mất một câu trả lời giữa chừng — và lỗi
 * đó chỉ xuất hiện với câu trả lời dài, tức là đúng lúc khó gỡ nhất.
 */

import { goiTho } from "./api";

export type SuKien = {
  type: string;
  [k: string]: unknown;
};

export async function hoi(
  than: Record<string, unknown>,
  onSuKien: (e: SuKien) => void,
  duong = "/api/chat/ask",
): Promise<void> {
  const r = await goiTho(duong, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(than),
  });

  if (!r.ok || !r.body) {
    onSuKien({
      type: "error",
      code: String(r.status),
      message:
        r.status === 401
          ? "Phiên đăng nhập đã hết hạn."
          : `Máy chủ trả về ${r.status}.`,
    });
    return;
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let dem = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    dem += decoder.decode(value, { stream: true });
    const goi = dem.split("\n\n");
    // Phần tử cuối có thể là một sự kiện chưa nhận đủ — giữ lại chờ lần sau.
    dem = goi.pop() ?? "";

    for (const g of goi) {
      if (!g.startsWith("data: ")) continue;
      try {
        onSuKien(JSON.parse(g.slice(6)) as SuKien);
      } catch {
        /* gói hỏng thì bỏ qua, không làm chết cả luồng */
      }
    }
  }
}
