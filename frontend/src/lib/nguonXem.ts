/**
 * Nguồn dữ liệu cho cột xem tài liệu.
 *
 * Cùng một trình xem chạy ở hai chỗ đọc dữ liệu theo hai đường khác hẳn nhau:
 *
 * * **màn hình làm việc** — `/api/notebooks/{nb}/…`, mỗi request gắn
 *   `Authorization` và tự làm mới token khi hết hạn;
 * * **trang chia sẻ** — `/api/shared/{token}/…`, không có phiên đăng nhập nào
 *   để gắn, và quyền nằm trong chính đường dẫn.
 *
 * Trước đây khác biệt ấy nằm rải trong các component, nên trang chia sẻ chỉ
 * hiện được chữ: nó không gọi được những endpoint mà trình xem cần. Gom lại
 * thành một giao diện thì trình xem không còn biết mình đang phục vụ ai, và
 * thêm một đường thứ ba về sau chỉ là viết thêm một cài đặt.
 */

import { GOC_API, goi, goiTho } from "@/lib/api";

export type HopToaDo = {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

export type ChiTietTrichDan = {
  chunk_id: number;
  content: string;
  page_no: number | null;
  heading_path: string | null;
  char_start: number;
  char_end: number;
  bbox: HopToaDo[] | null;
  source: { id: string; title: string; kind: string; pages: number | null };
};

export type VanBanNguon = {
  full_text: string;
  page_map: { page: number; start: number; end: number }[];
};

export type NguonXem = {
  /** Chi tiết một đoạn được trích dẫn, kèm toạ độ để tô sáng. */
  trichDan: (chunkId: number) => Promise<ChiTietTrichDan>;
  /** Byte gốc của tệp — PDF cho PDF.js, ảnh cho `<img>`. */
  tep: (sourceId: string) => Promise<Response>;
  /** Toàn văn đã chuẩn hoá, đúng chuỗi mà offset của chunk trỏ vào (INV-1). */
  vanBan: (sourceId: string) => Promise<VanBanNguon>;
};

/** Tài liệu trong notebook của chính người đang đăng nhập. */
export function nguonCuaToi(nbId: string): NguonXem {
  const goc = `/api/notebooks/${nbId}/sources`;
  return {
    trichDan: (chunkId) => goi<ChiTietTrichDan>(`/api/citations/${chunkId}`),
    tep: (sourceId) => goiTho(`${goc}/${sourceId}/file`),
    vanBan: (sourceId) => goi<VanBanNguon>(`${goc}/${sourceId}/text`),
  };
}

/**
 * Tài liệu mở qua một liên kết chia sẻ.
 *
 * Dùng `fetch` trần chứ không `goi()`: `goi()` gắn `Authorization` rồi coi 401
 * là tín hiệu làm mới token, mà ở đây không có phiên đăng nhập nào — người xem
 * có thể chưa từng có tài khoản.
 */
export function nguonChiaSe(token: string): NguonXem {
  const goc = `${GOC_API}/api/shared/${token}`;

  async function lay<T>(duong: string): Promise<T> {
    const r = await fetch(duong);
    if (!r.ok) throw new Error(String(r.status));
    return (await r.json()) as T;
  }

  return {
    trichDan: (chunkId) => lay<ChiTietTrichDan>(`${goc}/citations/${chunkId}`),
    tep: (sourceId) => fetch(`${goc}/sources/${sourceId}/file`),
    vanBan: (sourceId) => lay<VanBanNguon>(`${goc}/sources/${sourceId}/text`),
  };
}
