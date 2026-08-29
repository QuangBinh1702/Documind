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
  signal?: AbortSignal,
): Promise<void> {
  let r: Response;
  try {
    r = await goiTho(duong, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(than),
      signal,
    });
  } catch (err) {
    // Người dùng bấm dừng trước khi máy chủ kịp trả về dòng đầu tiên. Đó là
    // một kết thúc bình thường, không phải lỗi cần hiện trong khung chat.
    if (err instanceof DOMException && err.name === "AbortError") return;
    throw err;
  }

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

  await docLuong(r, onSuKien);
}

/**
 * Theo dõi một luồng SSE mở bằng `GET` — US-022.
 *
 * `EventSource` sẽ gọn hơn, nhưng nó không gắn được `Authorization`, và luồng
 * này nằm sau đăng nhập. Đưa token vào query string thì nó lọt vào log máy chủ
 * và lịch sử trình duyệt — nên vẫn dùng `fetch`.
 *
 * `signal` để giao diện đóng luồng khi rời khỏi notebook. Không có nó thì mỗi
 * lần chuyển notebook lại bỏ lại một kết nối chạy tiếp trong nền.
 */
export async function theoDoi(
  duong: string,
  onSuKien: (e: SuKien) => void,
  signal?: AbortSignal,
): Promise<void> {
  let r: Response;
  try {
    r = await goiTho(duong, { signal });
  } catch (err) {
    // Bị huỷ trước khi máy chủ kịp trả về — rời trang, hoặc React StrictMode
    // dựng rồi dỡ hiệu ứng một lần lúc phát triển. Kết thúc bình thường.
    if (err instanceof DOMException && err.name === "AbortError") return;
    throw err;
  }
  if (!r.ok || !r.body) return;
  await docLuong(r, onSuKien);
}

async function docLuong(r: Response, onSuKien: (e: SuKien) => void): Promise<void> {
  const reader = r.body!.getReader();
  const decoder = new TextDecoder();
  let dem = "";

  for (;;) {
    let doc;
    try {
      doc = await reader.read();
    } catch {
      // Luồng bị huỷ (rời trang, đổi notebook) — đó là kết thúc bình thường,
      // không phải lỗi cần báo cho người dùng.
      return;
    }
    const { done, value } = doc;
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
