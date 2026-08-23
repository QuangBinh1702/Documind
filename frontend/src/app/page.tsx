"use client";

/**
 * Đăng nhập và đăng ký — US-002, US-003.
 *
 * Một trang cho cả hai việc. Người dùng mới và người quay lại đến cùng một chỗ,
 * và chuyển qua lại không mất thứ đã gõ.
 *
 * Kiểm tra đầu vào chạy **trước khi gọi API** (US-002 AC-3): gõ sai định dạng
 * email thì thấy lỗi ngay, không phải đợi một vòng mạng để biết.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api, token } from "@/lib/api";

const EMAIL_HOP_LE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const MAT_KHAU_TOI_THIEU = 8;

export default function TrangDangNhap() {
  const router = useRouter();
  const [dangKy, setDangKy] = useState(false);
  const [email, setEmail] = useState("");
  const [matKhau, setMatKhau] = useState("");
  const [loi, setLoi] = useState<string | null>(null);
  const [dangGui, setDangGui] = useState(false);
  const [dangKiemTra, setDangKiemTra] = useState(true);

  // Đã có phiên còn hạn thì vào thẳng, không bắt đăng nhập lại.
  useEffect(() => {
    if (!token.access()) {
      setDangKiemTra(false);
      return;
    }
    api
      .toiLaAi()
      .then(() => router.replace("/notebooks"))
      .catch(() => {
        token.xoa();
        setDangKiemTra(false);
      });
  }, [router]);

  const loiEmail = email && !EMAIL_HOP_LE.test(email) ? "Email không đúng định dạng." : null;
  const loiMatKhau =
    matKhau && matKhau.length < MAT_KHAU_TOI_THIEU
      ? `Mật khẩu phải có ít nhất ${MAT_KHAU_TOI_THIEU} ký tự.`
      : null;
  const guiDuoc =
    EMAIL_HOP_LE.test(email) && matKhau.length >= MAT_KHAU_TOI_THIEU && !dangGui;

  async function gui(e: React.FormEvent) {
    e.preventDefault();
    if (!guiDuoc) return;
    setLoi(null);
    setDangGui(true);
    try {
      const cap = await (dangKy ? api.dangKy : api.dangNhap)(email, matKhau);
      token.luu(cap);
      router.replace("/notebooks");
    } catch (err) {
      setLoi(err instanceof ApiError ? err.message : "Không kết nối được máy chủ.");
      setDangGui(false);
    }
  }

  if (dangKiemTra) {
    return (
      <main className="grid h-full place-items-center">
        <p className="text-sm text-mo">Đang kiểm tra phiên đăng nhập…</p>
      </main>
    );
  }

  return (
    <main className="grid h-full place-items-center px-6">
      <div className="w-full max-w-sm">
        <h1 className="text-xl font-semibold tracking-tight">DocuMind</h1>
        <p className="mt-1 text-sm text-mo">
          Hỏi đáp trên tài liệu của bạn, luôn kèm trích dẫn kiểm chứng được.
        </p>

        <form onSubmit={gui} className="mt-8 space-y-4" noValidate>
          <Truong
            nhan="Email"
            loi={loiEmail}
            input={
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-md border border-vien bg-the px-3 py-2 outline-none focus:border-nhan"
                placeholder="ban@truong.edu.vn"
              />
            }
          />

          <Truong
            nhan="Mật khẩu"
            loi={loiMatKhau}
            input={
              <input
                type="password"
                autoComplete={dangKy ? "new-password" : "current-password"}
                value={matKhau}
                onChange={(e) => setMatKhau(e.target.value)}
                className="w-full rounded-md border border-vien bg-the px-3 py-2 outline-none focus:border-nhan"
                placeholder="ít nhất 8 ký tự"
              />
            }
          />

          {loi && (
            <p
              role="alert"
              className="rounded-md border border-canh-bao bg-canh-bao-nen px-3 py-2 text-sm text-canh-bao"
            >
              {loi}
            </p>
          )}

          <button
            type="submit"
            disabled={!guiDuoc}
            className="w-full rounded-md bg-nhan px-4 py-2 font-medium text-white disabled:opacity-45"
          >
            {dangGui ? "Đang xử lý…" : dangKy ? "Tạo tài khoản" : "Đăng nhập"}
          </button>
        </form>

        <button
          onClick={() => {
            setDangKy(!dangKy);
            setLoi(null);
          }}
          className="mt-5 text-sm text-nhan underline underline-offset-4"
        >
          {dangKy ? "Đã có tài khoản? Đăng nhập" : "Chưa có tài khoản? Đăng ký"}
        </button>
      </div>
    </main>
  );
}

function Truong({
  nhan,
  loi,
  input,
}: {
  nhan: string;
  loi: string | null;
  input: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">{nhan}</span>
      {input}
      {/* Lỗi hiện ngay tại trường nhập, trước khi gọi API — US-002 AC-3. */}
      {loi && <span className="mt-1 block text-xs text-canh-bao">{loi}</span>}
    </label>
  );
}
