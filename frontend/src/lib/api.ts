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
 *
 * `NEXT_PUBLIC_API_URL` được **nướng vào bundle lúc build**. Khi phát triển,
 * `.env.development` đặt nó là `http://localhost:8000`. Khi triển khai thật thì
 * KHÔNG đặt: gốc API rơi về chính origin đang mở trang, và reverse proxy
 * (Caddy) chuyển `/api/*` sang FastAPI — nhờ vậy một ảnh build chạy được ở mọi
 * tên miền, và CORS không còn là vấn đề.
 */
export const GOC_API =
  process.env.NEXT_PUBLIC_API_URL ??
  (typeof window !== "undefined" ? window.location.origin : "http://localhost:8000");

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
  /** Chỉ luồng SSE gửi trường này — mô tả cụ thể bước đang chạy (US-022). */
  message?: string;
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

export type DoTre = {
  so_luot: number;
  trung_binh_ms: number;
  p95_ms: number;
};

export type ThongKe = {
  so_notebook: number;
  so_nguon: number;
  so_chunk: number;
  dung_luong_bytes: number;
  so_luot_goi_ngoai: number;
  so_luot_tu_cache: number;
  ty_le_cache_hit: number;
  so_ban_ghi_cache: number;
  do_tre_privacy: DoTre;
  do_tre_fast: DoTre;
  phan_bo_answer_kind: Record<string, number>;
  luot_hoi_theo_ngay: { ngay: string; so_luot: number }[];
};

export type LienKetChiaSe = {
  token: string;
  duong_dan: string;
  con_hieu_luc: boolean;
  /** Phiên được chia sẻ. `null` là liên kết mức notebook, không kèm hội thoại. */
  session_id: string | null;
};

export type PhienHoiThoai = {
  id: string;
  title: string;
  updated_at: string;
};

export type TinNhan = {
  id: string;
  role: "user" | "assistant";
  content: string;
  answer_kind: string | null;
  model_used: string | null;
  latency_ms: number | null;
  citations: {
    marker: number;
    chunk_id: number | null;
    snippet: string;
    page: number | null;
    /** Nguồn đã bị xoá — chip hiện mờ, không bấm được (US-020 AC-4). */
    deleted: boolean;
  }[];
};

/** Tin nhắn nhìn từ phía người xem — không kèm chi tiết vận hành. */
export type TinNhanChiaSe = Omit<TinNhan, "model_used" | "latency_ms">;

export type NotebookChiaSe = {
  title: string;
  nguon: {
    id: string;
    title: string;
    kind: string;
    page_count: number | null;
    status: string;
  }[];
  phien_id: string | null;
  phien_tieu_de: string | null;
  tin_nhan: TinNhanChiaSe[];
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

  /** Thu hồi refresh token ở máy chủ rồi xoá cả hai token ở máy này. */
  dangXuat: async () => {
    const rt = token.refresh();
    token.xoa();
    if (!rt) return;
    try {
      await fetch(`${GOC_API}/api/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      });
    } catch {
      /* mất mạng thì token vẫn tự hết hạn; phía máy này đã xoá rồi */
    }
  },

  doiMatKhau: (old_password: string, new_password: string) =>
    goi<CapToken>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ old_password, new_password }),
    }),

  danhSachPhien: (nbId: string) =>
    goi<PhienHoiThoai[]>(`/api/sessions?notebook_id=${nbId}`),

  tinNhanCuaPhien: (phienId: string) =>
    goi<TinNhan[]>(`/api/sessions/${phienId}/messages`),

  doiNgonNgu: (locale: "vi" | "en") =>
    goi<NguoiDung>("/api/auth/me", {
      method: "PATCH",
      body: JSON.stringify({ locale }),
    }),

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

  thongKe: () => goi<ThongKe>("/api/stats"),

  // Ba lời gọi dưới đây mang `session_id` vì một notebook có nhiều hội thoại,
  // và mỗi hội thoại có liên kết riêng — xem quyết định 0004.
  lienKetChiaSe: (nbId: string, phienId: string | null) =>
    goi<LienKetChiaSe | null>(
      `/api/notebooks/${nbId}/share${phienId ? `?session_id=${phienId}` : ""}`,
    ),

  taoLienKetChiaSe: (nbId: string, phienId: string | null) =>
    goi<LienKetChiaSe>(`/api/notebooks/${nbId}/share`, {
      method: "POST",
      body: JSON.stringify({ session_id: phienId }),
    }),

  thuHoiLienKetChiaSe: (nbId: string, phienId: string | null) =>
    goi<void>(
      `/api/notebooks/${nbId}/share${phienId ? `?session_id=${phienId}` : ""}`,
      { method: "DELETE" },
    ),

  /** Đường của người xem — cố ý KHÔNG đi qua `goi()` vì nó không cần token. */
  notebookChiaSe: (token: string) =>
    fetch(`${GOC_API}/api/shared/${token}`).then(async (r) => {
      if (!r.ok) throw new ApiError(r.status, "Liên kết không còn hiệu lực.");
      return (await r.json()) as NotebookChiaSe;
    }),

  /** Hội thoại của chính người đang đăng nhập, đặt ra qua liên kết này. */
  phienCuaToiTrongChiaSe: (token: string) =>
    goi<PhienHoiThoai[]>(`/api/shared/${token}/my-sessions`),

  tinNhanCuaToiTrongChiaSe: (token: string, phienId: string) =>
    goi<TinNhanChiaSe[]>(`/api/shared/${token}/my-sessions/${phienId}/messages`),

  trichDan: (chunkId: number) =>
    goi<{
      chunk_id: number;
      content: string;
      page_no: number | null;
      heading_path: string | null;
      char_start: number;
      char_end: number;
      bbox: { page: number; x0: number; y0: number; x1: number; y1: number }[] | null;
      source: { id: string; title: string; kind: string; pages: number | null };
    }>(`/api/citations/${chunkId}`),
};

/**
 * Tải một tệp do máy chủ sinh ra về máy — US-040 AC-4.
 *
 * Không dùng thẻ `<a href>` thẳng: đường xuất đòi `Authorization`, mà thẻ liên
 * kết thì không gắn header được. Nên tải bằng `fetch` rồi tạo một liên kết tạm
 * trỏ vào blob và bấm hộ.
 *
 * Tên tệp lấy từ `Content-Disposition` của máy chủ chứ không tự đặt ở đây: máy
 * chủ mới biết tên notebook, và để một chỗ đặt tên thì hai bên không lệch nhau.
 */
export async function taiVe(duong: string, tenDuPhong: string): Promise<void> {
  const r = await goiTho(duong);
  if (!r.ok) {
    // Máy chủ nói được lý do — "thiếu font tiếng Việt" là thứ người vận hành
    // sửa được, còn "không xuất được" thì không.
    let chiTiet: string | null = null;
    try {
      chiTiet = (await r.json())?.detail ?? null;
    } catch {
      /* thân không phải JSON */
    }
    throw new ApiError(r.status, typeof chiTiet === "string" ? chiTiet : "Không xuất được tệp.");
  }

  const cd = r.headers.get("Content-Disposition") ?? "";
  const ten = /filename="([^"]+)"/.exec(cd)?.[1] ?? tenDuPhong;

  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = ten;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Thu hồi ngay thì Safari huỷ lượt tải đang bắt đầu; đợi một nhịp là đủ.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/**
 * Tải tệp lên kèm tiến trình theo phần trăm — US-006 AC-6.
 *
 * Dùng `XMLHttpRequest` chứ không dùng `fetch`: `fetch` chưa có cách nào theo
 * dõi tiến trình phần **gửi lên**. Với tệp 50 MB thì đó là khác biệt giữa một
 * thanh tiến trình và một vòng xoay không biết bao giờ xong.
 */
export async function taiLen(
  nbId: string,
  file: File,
  onTienTrinh: (phanTram: number) => void,
): Promise<Nguon> {
  // Cùng quy tắc với `goiTho()`: gặp 401 thì làm mới token rồi gửi lại đúng
  // một lần. Trước đây đường tải lên đi XHR trần, nên sau 60 phút mọi lượt kéo
  // thả đều hỏng với "Chưa đăng nhập" trong khi phần còn lại của giao diện vẫn
  // âm thầm làm mới và chạy tiếp.
  try {
    return await _taiLenMotLan(nbId, file, onTienTrinh);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401 && token.refresh() && (await lamMoiMotLan())) {
      return _taiLenMotLan(nbId, file, onTienTrinh);
    }
    throw err;
  }
}

function _taiLenMotLan(
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
