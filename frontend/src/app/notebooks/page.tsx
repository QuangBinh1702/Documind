"use client";

/**
 * Danh sách notebook — US-005 AC-1, AC-2.
 *
 * Chưa đăng nhập mà vào thẳng URL này thì bị đẩy về trang đăng nhập (AC-4 của
 * US-003). Kiểm ở client là để trải nghiệm mượt; quyền thật vẫn do máy chủ giữ,
 * và nó trả 401 bất kể client nghĩ gì.
 */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, type Notebook, api, token } from "@/lib/api";
import { NutChuDe } from "@/components/NutChuDe";

export default function TrangNotebook() {
  const router = useRouter();
  const [ds, setDs] = useState<Notebook[] | null>(null);
  const [email, setEmail] = useState("");
  const [tieuDe, setTieuDe] = useState("");
  const [loi, setLoi] = useState<string | null>(null);

  const tai = useCallback(async () => {
    try {
      const [me, list] = await Promise.all([api.toiLaAi(), api.danhSachNotebook()]);
      setEmail(me.email);
      setDs(list);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        token.xoa();
        router.replace("/");
        return;
      }
      setLoi("Không tải được danh sách notebook.");
      setDs([]);
    }
  }, [router]);

  useEffect(() => {
    if (!token.access()) {
      router.replace("/");
      return;
    }
    void tai();
  }, [router, tai]);

  async function tao(e: React.FormEvent) {
    e.preventDefault();
    const t = tieuDe.trim();
    if (!t) return;
    try {
      const nb = await api.taoNotebook(t);
      setTieuDe("");
      // AC-2: mở ra ngay, không bắt bấm thêm một lần nữa.
      router.push(`/notebooks/${nb.id}`);
    } catch {
      setLoi("Không tạo được notebook.");
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-lg font-semibold tracking-tight">Notebook của bạn</h1>
        <div className="flex items-center gap-3 text-sm text-mo">
          <span>{email}</span>
          <NutChuDe />
          <Link href="/thong-ke" className="underline underline-offset-4">
            Số liệu
          </Link>
          <button
            onClick={() => {
              token.xoa();
              router.replace("/");
            }}
            className="underline underline-offset-4"
          >
            Đăng xuất
          </button>
        </div>
      </header>

      <form onSubmit={tao} className="mt-7 flex gap-2">
        <input
          value={tieuDe}
          onChange={(e) => setTieuDe(e.target.value)}
          placeholder="Tên notebook mới — ví dụ: Quy chế đào tạo"
          className="flex-1 rounded-md border border-vien bg-the px-3 py-2 outline-none focus:border-nhan"
        />
        <button
          type="submit"
          disabled={!tieuDe.trim()}
          className="rounded-md bg-nhan px-4 py-2 font-medium text-white disabled:opacity-45"
        >
          Tạo
        </button>
      </form>

      {/* Lỗi phải kèm một việc làm được, không chỉ là một câu buồn — US-042 AC-3. */}
      {loi && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-canh-bao bg-canh-bao-nen px-4 py-3">
          <p className="text-sm text-canh-bao">{loi}</p>
          <button
            onClick={() => {
              setLoi(null);
              setDs(null);
              void tai();
            }}
            className="rounded-md border border-canh-bao px-2.5 py-1 text-xs text-canh-bao"
          >
            Thử lại
          </button>
        </div>
      )}

      <div className="mt-8">
        {ds === null ? (
          // Khung xương thay cho màn hình trắng — AC-2. Nó cũng cho biết trước
          // trang sắp có hình dạng thế nào, nên lúc dữ liệu về không bị nhảy.
          <ul className="divide-y divide-vien rounded-lg border border-vien bg-the">
            {Array.from({ length: 3 }, (_, i) => (
              <li key={i} className="flex items-center justify-between px-5 py-5">
                <span className="h-4 w-48 animate-pulse rounded bg-vien" />
                <span className="h-3 w-24 animate-pulse rounded bg-vien" />
              </li>
            ))}
          </ul>
        ) : ds.length === 0 ? (
          // Trạng thái rỗng phải hướng dẫn, không phải khoảng trắng — US-042 AC-1.
          <div className="rounded-lg border border-dashed border-vien px-5 py-12 text-center">
            <ThuMucRong />
            <p className="mt-4 font-medium">Chưa có notebook nào</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-mo">
              Tạo một notebook cho mỗi môn học hoặc mỗi bộ tài liệu, rồi tải tệp
              vào đó. Hỏi trong notebook nào thì chỉ tìm trong tài liệu của
              notebook đó.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-vien rounded-lg border border-vien bg-the">
            {ds.map((nb) => (
              <li key={nb.id}>
                <Link
                  href={`/notebooks/${nb.id}`}
                  className="flex items-baseline justify-between gap-4 px-5 py-4 hover:bg-nen"
                >
                  <span className="font-medium">{nb.title}</span>
                  <span className="shrink-0 text-sm text-mo">
                    {nb.source_count === 0
                      ? "chưa có tài liệu"
                      : nb.ready_count === nb.source_count
                        ? `${nb.source_count} tài liệu`
                        : `${nb.ready_count}/${nb.source_count} tài liệu đã xử lý`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** Minh hoạ cho trạng thái rỗng. SVG viết tay — một hình đơn giản không đáng
 *  kéo theo cả một bộ icon, và nó ăn theo màu chữ nên tự đúng ở chế độ tối. */
function ThuMucRong() {
  return (
    <svg
      viewBox="0 0 96 72"
      className="mx-auto h-16 w-auto text-mo"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinejoin="round"
      aria-hidden="true"
      opacity={0.55}
    >
      <path d="M6 18a6 6 0 0 1 6-6h22l7 8h37a6 6 0 0 1 6 6v34a6 6 0 0 1-6 6H12a6 6 0 0 1-6-6z" />
      <path d="M30 40h36M30 50h24" strokeLinecap="round" opacity={0.6} />
    </svg>
  );
}
