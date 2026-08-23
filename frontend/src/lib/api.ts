/**
 * Tầng gọi API.
 *
 * Việc đáng nói nhất ở đây là **tự làm mới token** (US-003 AC-3): access token
 * sống 60 phút, và người dùng không được thấy gián đoạn khi nó hết hạn. Mọi lời
 * gọi đi qua `goi()`; gặp 401 thì nó đổi refresh token lấy cặp mới rồi **gửi
 * lại đúng request đó**.
 *
 * Nhiều request cùng hết hạn một lúc là chuyện bình thường — mở một notebook
 * gọi song song ba endpoint. Nếu mỗi cái tự đi refresh thì lần đầu thành công,
 * những lần sau dùng refresh token đã bị thay và hỏng. Vì vậy lượt refresh đang
 * chạy được giữ trong `dangLamMoi` để mọi request cùng đợi chung một lượt.
 *
 * Token để ở `localStorage`
 * -------------------------
 * Đánh đổi có ý thức, và là hạn chế phải nêu trong báo cáo: cookie `httpOnly`
 * an toàn hơn trước XSS vì mã JavaScript không đọc được. Đổi lại nó cần cùng
 * site hoặc phải cấu hình CSRF, và làm phần triển khai phức tạp hơn hẳn.
 * `localStorage` chấp nhận được ở phạm vi đồ án vì access token chỉ sống 60
 * phút, nhưng nó **không** phải lựa chọn đúng cho một hệ thống thật.
 */

/**
 * Gốc của API. Trình duyệt gọi thẳng FastAPI, không qua proxy của Next —
 * `next.config.ts` giải thích vì sao (tóm tắt: proxy đệm mất streaming).
 */
export const GOC_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const KHOA_ACCESS = "documind.access";
const KHOA_REFRESH = "documind.refresh";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export const token = {
  access: () => localStorage.getItem(KHOA_ACCESS),
  refresh: () => localStorage.getItem(KHOA_REFRESH),
  luu(cap: { access_token: string; refresh_token: string }) {
    localStorage.setItem(KHOA_ACCESS, cap.access_token);
    localStorage.setItem(KHOA_REFRESH, cap.refresh_token);
  },
  xoa() {
    localStorage.removeItem(KHOA_ACCESS);
    localStorage.removeItem(KHOA_REFRESH);
  },
};

let dangLamMoi: Promise<boolean> | null = null;

async function lamMoi(): Promise<boolean> {
  const rt = token.refresh();
  if (!rt) return false;

  const r = await fetch(`${GOC_API}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: rt }),
  });
  if (!r.ok) {
    token.xoa();
    return false;
  }
  token.luu(await r.json());
  return true;
}

function lamMoiMotLan(): Promise<boolean> {
  dangLamMoi ??= lamMoi().finally(() => {
    dangLamMoi = null;
  });
  return dangLamMoi;
}

async function _goi(duong: string, init: RequestInit): Promise<Response> {
  const at = token.access();
  const headers = new Headers(init.headers);
  if (at) headers.set("Authorization", `Bearer ${at}`);
  return fetch(`${GOC_API}${duong}`, { ...init, headers });
}

/** Gọi API, tự làm mới token một lần khi gặp 401. */
export async function goiTho(duong: string, init: RequestInit = {}): Promise<Response> {
  let r = await _goi(duong, init);
  if (r.status === 401 && token.refresh() && (await lamMoiMotLan())) {
    r = await _goi(duong, init);
  }
  return r;
}

async function doc<T>(r: Response): Promise<T> {
  if (r.status === 204) return undefined as T;
  const noiDung = await r.text();
  const data = noiDung ? JSON.parse(noiDung) : null;
  if (!r.ok) {
    const detail = data?.detail;
    throw new ApiError(
      r.status,
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? (detail[0]?.msg ?? "Dữ liệu không hợp lệ.")
          : "Có lỗi xảy ra.",
    );
  }
  return data as T;
}

export async function goi<T>(duong: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  return doc<T>(await goiTho(duong, { ...init, headers }));
}

// ── Kiểu dữ liệu ───────────────────────────────────────

export type CapToken = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

export type NguoiDung = {
  id: string;
  email: string;
  locale: string;
  role: string;
};

export type Notebook = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  source_count: number;
  ready_count: number;
};

export type Nguon = {
  id: string;
  title: string;
  original_name: string;
  kind: string;
  size_bytes: number;
  page_count: number | null;
  status: string;
  progress: number;
  text_quality: number | null;
  error_code: string | null;
  error_message: string | null;
  in_scope: boolean;
  created_at: string;
};

export type TrichDan = {
  marker: number;
  chunk_id: number;
  source_id: string;
  page: number | null;
  char_start: number;
  char_end: number;
  snippet: string;
  heading_path: string | null;
};

// ── Các lời gọi cụ thể ─────────────────────────────────

export const api = {
  dangKy: (email: string, password: string) =>
    goi<CapToken>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  dangNhap: (email: string, password: string) =>
    goi<CapToken>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  toiLaAi: () => goi<NguoiDung>("/api/auth/me"),

  danhSachNotebook: () => goi<Notebook[]>("/api/notebooks"),

  taoNotebook: (title: string) =>
    goi<Notebook>("/api/notebooks", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),

  motNotebook: (id: string) => goi<Notebook>(`/api/notebooks/${id}`),

  doiTenNotebook: (id: string, title: string) =>
    goi<Notebook>(`/api/notebooks/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  xoaNotebook: (id: string) =>
    goi<void>(`/api/notebooks/${id}`, { method: "DELETE" }),

  danhSachNguon: (nbId: string) => goi<Nguon[]>(`/api/notebooks/${nbId}/sources`),

  xoaNguon: (nbId: string, id: string) =>
    goi<void>(`/api/notebooks/${nbId}/sources/${id}`, { method: "DELETE" }),

  doiPhamVi: (nbId: string, id: string, inScope: boolean) =>
    goi<Nguon>(`/api/notebooks/${nbId}/sources/${id}?in_scope=${inScope}`, {
      method: "PATCH",
    }),

  cauHinh: () =>
    goi<{ du_lieu_roi_khoi_may: boolean; che_do: string }>("/api/config"),

  trichDan: (chunkId: number) =>
    goi<{
      chunk_id: number;
      content: string;
      page_no: number | null;
      heading_path: string | null;
      char_start: number;
      char_end: number;
      source: { id: string; title: string };
    }>(`/api/citations/${chunkId}`),
};

/**
 * Tải tệp lên kèm tiến trình theo phần trăm — US-006 AC-6.
 *
 * Dùng `XMLHttpRequest` chứ không dùng `fetch`: `fetch` chưa có cách nào theo
 * dõi tiến trình phần **gửi lên**. Với tệp 50 MB thì đó là khác biệt giữa một
 * thanh tiến trình và một vòng xoay không biết bao giờ xong.
 */
export function taiLen(
  nbId: string,
  file: File,
  onTienTrinh: (phanTram: number) => void,
): Promise<Nguon> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${GOC_API}/api/notebooks/${nbId}/sources`);
    const at = token.access();
    if (at) xhr.setRequestHeader("Authorization", `Bearer ${at}`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onTienTrinh(Math.round((e.loaded / e.total) * 100));
    };

    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* phản hồi rỗng hoặc không phải JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data as Nguon);
      } else {
        const detail = (data as { detail?: string } | null)?.detail;
        reject(new ApiError(xhr.status, detail ?? "Tải tệp thất bại."));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Mất kết nối khi tải tệp."));
    xhr.send(form);
  });
}
