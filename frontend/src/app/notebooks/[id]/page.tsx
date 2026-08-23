"use client";

/**
 * Màn hình làm việc chính — US-016.
 *
 * Trang này giữ trạng thái chung của ba cột và một việc nữa: **theo dõi tiến
 * trình xử lý tài liệu**. Tải một tệp lên xong thì nó chưa hỏi được ngay; máy
 * chủ trả `202` rồi xử lý ở nền. Nên khi còn nguồn nào chưa xong, trang hỏi lại
 * danh sách mỗi hai giây, và dừng hỏi ngay khi mọi thứ đã xong — không có lý do
 * gì để một trang tĩnh gọi API mãi mãi.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, type Nguon, type Notebook, type TrichDan, api, token } from "@/lib/api";
import { BaCot } from "@/components/BaCot";
import { CotHoiDap } from "@/components/CotHoiDap";
import { CotNguon } from "@/components/CotNguon";
import { CotTaiLieu } from "@/components/CotTaiLieu";
import { NhanQuyenRiengTu } from "@/components/NhanQuyenRiengTu";

const NHIP_HOI_LAI_MS = 2000;

export default function ManHinhNotebook() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [nb, setNb] = useState<Notebook | null>(null);
  const [nguon, setNguon] = useState<Nguon[]>([]);
  const [trichDan, setTrichDan] = useState<TrichDan | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [dangSuaTen, setDangSuaTen] = useState(false);
  const dongHo = useRef<ReturnType<typeof setTimeout> | null>(null);

  const tai = useCallback(async () => {
    try {
      const [thongTin, ds] = await Promise.all([
        api.motNotebook(id),
        api.danhSachNguon(id),
      ]);
      setNb(thongTin);
      setNguon(ds);
      return ds;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        token.xoa();
        router.replace("/");
      } else if (err instanceof ApiError && err.status === 404) {
        setLoi("Không tìm thấy notebook này.");
      } else {
        setLoi("Không tải được notebook.");
      }
      return [];
    }
  }, [id, router]);

  useEffect(() => {
    if (!token.access()) {
      router.replace("/");
      return;
    }
    void tai();
  }, [router, tai]);

  // Hỏi lại chừng nào còn nguồn đang xử lý, rồi dừng hẳn.
  useEffect(() => {
    const dangChay = nguon.some((s) => s.status !== "ready" && s.status !== "failed");
    if (!dangChay) return;

    dongHo.current = setTimeout(() => void tai(), NHIP_HOI_LAI_MS);
    return () => {
      if (dongHo.current) clearTimeout(dongHo.current);
    };
  }, [nguon, tai]);

  if (loi) {
    return (
      <main className="grid h-full place-items-center px-6 text-center">
        <div>
          <p className="font-medium">{loi}</p>
          <Link href="/notebooks" className="mt-3 inline-block text-sm text-nhan underline">
            Về danh sách notebook
          </Link>
        </div>
      </main>
    );
  }

  const sanSang = nguon.some((s) => s.status === "ready" && s.in_scope);

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-vien px-5 py-3">
        <Link href="/notebooks" className="text-sm text-mo hover:text-chu">
          ← Notebook
        </Link>

        {dangSuaTen && nb ? (
          <input
            autoFocus
            defaultValue={nb.title}
            onBlur={async (e) => {
              const t = e.target.value.trim();
              setDangSuaTen(false);
              if (t && t !== nb.title) {
                const moi = await api.doiTenNotebook(id, t);
                setNb(moi);
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
              if (e.key === "Escape") setDangSuaTen(false);
            }}
            className="rounded-md border border-nhan bg-the px-2 py-1 font-medium outline-none"
          />
        ) : (
          <button
            onClick={() => setDangSuaTen(true)}
            title="Bấm để đổi tên"
            className="font-medium tracking-tight"
          >
            {nb?.title ?? "…"}
          </button>
        )}

        <span className="ml-auto text-xs text-mo">
          {nguon.length === 0
            ? "chưa có tài liệu"
            : `${nguon.filter((s) => s.status === "ready").length}/${nguon.length} tài liệu đã xử lý`}
        </span>
        <NhanQuyenRiengTu />
      </header>

      <div className="min-h-0 flex-1">
        <BaCot
          nguon={<CotNguon nbId={id} nguon={nguon} onDoiThay={() => void tai()} />}
          hoiDap={
            <CotHoiDap nbId={id} sanSang={sanSang} onChonTrichDan={setTrichDan} />
          }
          xemTaiLieu={<CotTaiLieu trichDan={trichDan} />}
        />
      </div>
    </div>
  );
}
