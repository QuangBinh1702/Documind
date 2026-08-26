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
import { NutChiaSe } from "@/components/NutChiaSe";
import { NutNgonNgu, useNgonNgu } from "@/components/NgonNguProvider";

export default function ManHinhNotebook() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [nb, setNb] = useState<Notebook | null>(null);
  const [nguon, setNguon] = useState<Nguon[]>([]);
  const [trichDan, setTrichDan] = useState<TrichDan | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [dangSuaTen, setDangSuaTen] = useState(false);
  const [vuaXong, setVuaXong] = useState<string | null>(null);
  const [thongBao, setThongBao] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("hoi");
  const { t } = useNgonNgu();
  const daXong = useRef<Set<string>>(new Set());
  // Đánh thức vòng lặp theo dõi khi có tệp mới, mà không phải dựng lại hiệu ứng
  // — dựng lại chính là thứ đã giết luồng đang chạy ở bản trước.
  const bao = useRef<() => void>(() => {});

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
        setLoi(t("nb.khongTimThay"));
      } else {
        setLoi(t("nb.khongTaiDuoc"));
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
  // Phụ thuộc CHỈ vào `id`, không vào `nguon`.
  //
  // Bản trước để `nguon.length` trong danh sách phụ thuộc, và nó tự phá chính
  // mình: luồng đẩy về một tài liệu mới → `setNguon` → độ dài đổi → React dọn
  // hiệu ứng → `abort()` giết đúng cái luồng vừa gửi dữ liệu → mở luồng khác →
  // lặp lại. Người dùng thấy trạng thái đứng im ở "đang chờ 0%" trong khi máy
  // chủ đã xử lý xong từ lâu, và log máy chủ đầy những lượt mở luồng liên tiếp.
  //
  // Giờ vòng lặp tự nối lại: máy chủ đóng luồng khi mọi thứ đã xong, và một
  // lượt tải lên bấm `bao.current()` để mở lại ngay.
  useEffect(() => {
    if (!token.access()) return;

    const dung = new AbortController();
    let huy = false;

    // Đánh thức vòng lặp mà không phải dựng lại hiệu ứng.
    let danhThuc: (() => void) | null = null;
    bao.current = () => danhThuc?.();

    const doiTinHieu = () =>
      new Promise<void>((giai_quyet) => {
        danhThuc = giai_quyet;
        // Vẫn hỏi lại sau một phút kể cả khi không ai bấm gì: một sự kiện bị
        // rơi không được biến thành trạng thái sai vĩnh viễn.
        setTimeout(giai_quyet, 60_000);
      });

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

        // Luồng đã đóng — hoặc vì mọi nguồn đã xong, hoặc vì hết hạn. Lấy lại
        // bản đầy đủ rồi ngủ cho tới khi có tệp mới.
        await tai();
        if (huy) return;
        await doiTinHieu();
      }
    }

    void chay();
    return () => {
      huy = true;
      danhThuc?.();
      bao.current = () => {};
      dung.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loi) {
    return (
      <main className="grid h-full place-items-center px-6 text-center">
        <div>
          <p className="font-medium">{loi}</p>
          <Link href="/notebooks" className="mt-3 inline-block text-sm text-nhan underline">
            {t("nb.veDanhSach")}
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
          ← {t("tk.notebook")}
        </Link>

        {dangSuaTen && nb ? (
          <input
            autoFocus
            defaultValue={nb.title}
            onBlur={async (e) => {
              const ten = e.target.value.trim();
              setDangSuaTen(false);
              if (ten && ten !== nb.title) {
                try {
                  setNb(await api.doiTenNotebook(id, ten));
                } catch {
                  setVuaXong(null);
                  setThongBao(t("loi.khongLuuDuoc"));
                }
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
            title={t("nb.doiTen")}
            className="font-medium tracking-tight"
          >
            {nb?.title ?? "…"}
          </button>
        )}

        <span className="ml-auto text-xs text-mo">
          {nguon.length === 0
            ? t("nb.chuaCoTaiLieu")
            : t("nb.daXuLy", {
                xong: nguon.filter((s) => s.status === "ready").length,
                tong: nguon.length,
              })}
        </span>
        <NutChiaSe nbId={id} />
        <NhanQuyenRiengTu />
        <NutNgonNgu />
        <NutChuDe />
        {/* US-005 AC-4 — xoá notebook và mọi thứ bên trong. */}
        <button
          onClick={async () => {
            if (!nb || !confirm(t("nb.xoaHoi", { ten: nb.title }))) return;
            try {
              await api.xoaNotebook(id);
              router.replace("/notebooks");
            } catch {
              setThongBao(t("loi.khongLuuDuoc"));
            }
          }}
          title={t("nb.xoa")}
          className="rounded-md border border-vien px-2 py-0.5 text-xs text-mo hover:border-canh-bao hover:text-canh-bao"
        >
          ✕
        </button>
      </header>

      {thongBao && (
        <div
          role="alert"
          className="flex shrink-0 items-center gap-3 border-b border-canh-bao bg-canh-bao-nen px-5 py-2 text-sm text-canh-bao"
        >
          <span className="flex-1">{thongBao}</span>
          <button onClick={() => setThongBao(null)} className="text-xs underline">
            {t("chung.dong")}
          </button>
        </div>
      )}

      {/* US-022 AC-4 — báo khi tài liệu sẵn sàng, rồi tự biến mất. */}
      {vuaXong && (
        <div
          role="status"
          className="shrink-0 border-b border-vien bg-nhan/5 px-5 py-2 text-sm"
        >
          {t("nguon.datXong", { ten: vuaXong })}
        </div>
      )}

      <div className="min-h-0 flex-1">
        <BaCot
          tab={tab}
          onDoiTab={setTab}
          nguon={
            <CotNguon
              nbId={id}
              nguon={nguon}
              onDoiThay={async () => {
                await tai();
                // Mở lại luồng ngay để thấy tiến độ của tệp vừa thêm.
                bao.current();
              }}
            />
          }
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
