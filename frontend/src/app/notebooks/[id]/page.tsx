"use client";

/**
 * Màn hình làm việc chính — US-016.
 *
 * Trang này giữ trạng thái chung của ba cột và một việc nữa: **theo dõi tiến
 * trình xử lý tài liệu** (US-022). Tải một tệp lên xong thì nó chưa hỏi được
 * ngay; máy chủ trả `202` rồi xử lý ở nền.
 *
 * Trạng thái tới qua một luồng SSE chứ không phải hỏi lại theo nhịp. Khác biệt
 * không chỉ là ít request hơn: hỏi lại mỗi hai giây thì bước OCR
 * *"45/120 trang"* đứng yên hai giây một lần và nhìn như bị treo, còn luồng thì
 * đẩy sang ngay khi có thay đổi.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, type Nguon, type Notebook, type TrichDan, api, token } from "@/lib/api";
import { theoDoi, type SuKien } from "@/lib/stream";
import { BaCot, type Tab } from "@/components/BaCot";
import { CotHoiDap } from "@/components/CotHoiDap";
import { CotNguon } from "@/components/CotNguon";
import { CotTaiLieu } from "@/components/CotTaiLieu";
import { NhanQuyenRiengTu } from "@/components/NhanQuyenRiengTu";
import { NutChuDe } from "@/components/NutChuDe";
import { MatKetNoi } from "@/components/MatKetNoi";

export default function ManHinhNotebook() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [nb, setNb] = useState<Notebook | null>(null);
  const [nguon, setNguon] = useState<Nguon[]>([]);
  const [trichDan, setTrichDan] = useState<TrichDan | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [dangSuaTen, setDangSuaTen] = useState(false);
  const [vuaXong, setVuaXong] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("hoi");
  const daXong = useRef<Set<string>>(new Set());

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

  // Luồng trạng thái — US-022 AC-1.
  //
  // Máy chủ tự đóng luồng khi mọi nguồn đã xong, nên vòng lặp này không phải là
  // hỏi lại liên tục: nó chỉ mở lại khi có tệp mới được tải lên, và ngồi im
  // trong lúc chờ.
  useEffect(() => {
    if (!token.access()) return;
    const dung = new AbortController();
    let huy = false;

    async function chay() {
      while (!huy) {
        await theoDoi(
          `/api/notebooks/${id}/sources/stream`,
          (e: SuKien) => {
            if (e.type !== "sources") return;
            const ds = e.sources as Nguon[];
            setNguon((cu) =>
              // Luồng chỉ gửi những trường thay đổi theo thời gian. Trộn lên
              // bản đầy đủ để không xoá mất `size_bytes`, `text_quality`…
              ds.map((moi) => ({ ...cu.find((c) => c.id === moi.id), ...moi }) as Nguon),
            );

            // AC-4: báo khi một tài liệu vừa sẵn sàng, mỗi tài liệu một lần.
            for (const s of ds) {
              if (s.status === "ready" && !daXong.current.has(s.id)) {
                daXong.current.add(s.id);
                setVuaXong(s.title);
                setTimeout(() => setVuaXong(null), 4000);
              }
            }
          },
          dung.signal,
        );
        if (huy) return;
        // Luồng đóng vì mọi thứ đã xong. Lấy lại bản đầy đủ một lần rồi nghỉ;
        // lượt tải lên tiếp theo sẽ gọi `tai()` và mở lại vòng này.
        await tai();
        return;
      }
    }

    void chay();
    return () => {
      huy = true;
      dung.abort();
    };
    // `nguon.length` để mở lại luồng khi có tệp mới, không phải mỗi lần đổi %.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, nguon.length]);

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
      <MatKetNoi />
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
        <NutChuDe />
      </header>

      {/* US-022 AC-4 — báo khi tài liệu sẵn sàng, rồi tự biến mất. */}
      {vuaXong && (
        <div
          role="status"
          className="shrink-0 border-b border-vien bg-nhan/5 px-5 py-2 text-sm"
        >
          <b className="font-medium">{vuaXong}</b> đã xử lý xong — hỏi được rồi.
        </div>
      )}

      <div className="min-h-0 flex-1">
        <BaCot
          tab={tab}
          onDoiTab={setTab}
          nguon={<CotNguon nbId={id} nguon={nguon} onDoiThay={() => void tai()} />}
          hoiDap={
            <CotHoiDap
              nbId={id}
              sanSang={sanSang}
              onChonTrichDan={setTrichDan}
              onTaiTaiLieu={() => setTab("nguon")}
            />
          }
          xemTaiLieu={<CotTaiLieu nbId={id} trichDan={trichDan} />}
        />
      </div>
    </div>
  );
}
