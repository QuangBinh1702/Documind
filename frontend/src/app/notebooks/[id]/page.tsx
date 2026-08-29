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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, type Nguon, type Notebook, type TrichDan, api, token } from "@/lib/api";
import { nguonCuaToi } from "@/lib/nguonXem";
import { theoDoi, type SuKien } from "@/lib/stream";
import { BaCot, type Tab } from "@/components/BaCot";
import { CotHoiDap } from "@/components/CotHoiDap";
import { CotNguon } from "@/components/CotNguon";
import { CotTaiLieu } from "@/components/CotTaiLieu";
import { NhanQuyenRiengTu } from "@/components/NhanQuyenRiengTu";
import { MatKetNoi } from "@/components/MatKetNoi";
import { MenuCaiDat } from "@/components/MenuCaiDat";
import { NutChiaSe } from "@/components/NutChiaSe";
import { Bt } from "@/components/BieuTuong";
import { useNgonNgu } from "@/components/NgonNguProvider";

/**
 * Menu "⋯" của notebook.
 *
 * Chỉ còn **xoá**. Trước đây menu này có thêm một mục *"Bấm để đổi tên"*, mà
 * bấm vào chỉ làm đúng một việc: mở ô sửa tên — thứ mà bấm thẳng vào tiêu đề đã
 * làm được rồi. Hai đường dẫn tới cùng một hành động, và đường nằm trong menu
 * lại là đường khó thấy hơn, nên nó chỉ tổ dạy người dùng đi tìm trong menu một
 * việc vốn nằm ngay trước mắt. Cách sửa đúng không phải là giữ cả hai mà là làm
 * cho tiêu đề **trông rõ là bấm được** — xem cây bút ở thanh tiêu đề bên dưới.
 *
 * Việc phá hoại thì vẫn nằm sau một lớp bấm, và đó là lý do menu này còn tồn
 * tại dù chỉ có một mục.
 */
function MenuNotebook({ onXoa }: { onXoa: () => void }) {
  const [mo, setMo] = useState(false);
  const { t } = useNgonNgu();
  return (
    <div className="relative">
      <button
        onClick={() => setMo((m) => !m)}
        aria-expanded={mo}
        aria-haspopup="menu"
        className="nut-icon"
        title={t("nb.tuyChon")}
      >
        <Bt.nhieuHon size={18} />
        <span className="sr-only">{t("nb.tuyChon")}</span>
      </button>
      {mo && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setMo(false)} />
          <div role="menu" className="menu-noi absolute right-0 z-30 mt-2 w-48 py-1.5">
            <button
              role="menuitem"
              className="muc-menu w-full text-canh-bao"
              onClick={() => {
                setMo(false);
                onXoa();
              }}
            >
              <Bt.xoa /> {t("nb.xoa")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

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
  const [email, setEmail] = useState<string | undefined>(undefined);
  const [tab, setTab] = useState<Tab>("hoi");
  // Phiên hội thoại đang mở, do cột giữa báo lên. Nút Chia sẻ cần nó để phát
  // liên kết trỏ đúng đoạn người dùng đang nhìn — xem quyết định 0004.
  const [phienId, setPhienId] = useState<string | null>(null);

  // Ổn định qua các lượt vẽ: `CotTaiLieu` nhận nguồn này trong mảng phụ thuộc
  // của một hiệu ứng, nên dựng mới mỗi lượt sẽ thành vòng lặp nạp vô tận.
  const nguonXem = useMemo(() => nguonCuaToi(id), [id]);

  useEffect(() => {
    if (!token.access()) return;
    api.toiLaAi().then((me) => setEmail(me.email)).catch(() => {});
  }, []);
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
      <header className="flex shrink-0 items-center gap-2 border-b border-vien px-4 py-2.5">
        <Link href="/notebooks" className="nut-icon" title={t("nb.veDanhSach")}>
          <Bt.quayLai size={18} />
          <span className="sr-only">{t("nb.veDanhSach")}</span>
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
          // Cây bút hiện khi rê chuột hoặc khi nút được focus bằng bàn phím.
          // Đây là thứ thay cho mục "đổi tên" đã bỏ khỏi menu "⋯": nó nói rằng
          // tiêu đề bấm được, ngay tại chỗ hành động sẽ xảy ra.
          <button
            onClick={() => setDangSuaTen(true)}
            title={t("nb.doiTen")}
            className="group flex min-w-0 items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[15px] font-semibold tracking-tight hover:bg-chu/5"
          >
            <span className="truncate">{nb?.title ?? "…"}</span>
            <Bt.but
              size={13}
              className="shrink-0 text-mo opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
            />
          </button>
        )}

        <span className="hidden text-xs text-mo sm:inline">
          {nguon.length === 0
            ? t("nb.chuaCoTaiLieu")
            : t("nb.daXuLy", {
                xong: nguon.filter((s) => s.status === "ready").length,
                tong: nguon.length,
              })}
        </span>

        <div className="ml-auto flex items-center gap-1">
          <NhanQuyenRiengTu />
          <NutChiaSe nbId={id} phienId={phienId} />
          <MenuNotebook
            onXoa={async () => {
              if (!nb || !confirm(t("nb.xoaHoi", { ten: nb.title }))) return;
              try {
                await api.xoaNotebook(id);
                router.replace("/notebooks");
              } catch {
                setThongBao(t("loi.khongLuuDuoc"));
              }
            }}
          />
          <MenuCaiDat email={email} />
        </div>
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
              nguon={nguon}
              sanSang={sanSang}
              onChonTrichDan={setTrichDan}
              onTaiTaiLieu={() => setTab("nguon")}
              onThemNguon={() => {
                void tai();
                // Mở lại luồng ngay để thấy tiến độ của ảnh vừa dán.
                bao.current();
              }}
              onDoiPhien={setPhienId}
            />
          }
          xemTaiLieu={<CotTaiLieu nguon={nguonXem} trichDan={trichDan} />}
        />
      </div>
    </div>
  );
}
