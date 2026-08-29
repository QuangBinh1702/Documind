"use client";

/**
 * Bố cục ba cột kéo được — US-016 AC-1, AC-2, AC-3.
 *
 * Dưới 1024px thì chuyển sang tab thay vì bóp ba cột lại (AC-3). Ba cột trên
 * màn hình điện thoại không phải là ba cột hẹp, nó là ba cột không đọc được.
 *
 * Độ rộng ghi vào `localStorage` để lần sau mở lại vẫn như cũ (AC-2). Người
 * dùng kéo cột nguồn rộng ra vì tên tài liệu của họ dài; bắt họ kéo lại mỗi lần
 * mở là một sự khó chịu nhỏ lặp lại mãi.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useNgonNgu } from "@/components/NgonNguProvider";

const KHOA = "documind.docrong";
const MIN = 220;
const MAX = 560;

export type Tab = "nguon" | "hoi" | "xem";

export function BaCot({
  nguon,
  hoiDap,
  xemTaiLieu,
  tab: tabNgoai,
  onDoiTab,
}: {
  nguon: React.ReactNode;
  hoiDap: React.ReactNode;
  xemTaiLieu: React.ReactNode;
  /** Điều khiển từ ngoài khi có chỗ khác cần mở một tab — ví dụ nút "tải tài
   *  liệu đầu tiên lên" nằm trong cột hội thoại. Bỏ trống thì tự quản lý. */
  tab?: Tab;
  onDoiTab?: (t: Tab) => void;
}) {
  const [rongTrai, setRongTrai] = useState(280);
  const [rongPhai, setRongPhai] = useState(380);
  const [tabTrong, setTabTrong] = useState<Tab>("hoi");
  const tab = tabNgoai ?? tabTrong;
  const setTab = onDoiTab ?? setTabTrong;
  const [hep, setHep] = useState(false);
  const keo = useRef<"trai" | "phai" | null>(null);
  const { t } = useNgonNgu();

  useEffect(() => {
    try {
      const luu = JSON.parse(localStorage.getItem(KHOA) ?? "{}");
      if (typeof luu.trai === "number") setRongTrai(luu.trai);
      if (typeof luu.phai === "number") setRongPhai(luu.phai);
    } catch {
      /* dữ liệu cũ hỏng thì dùng mặc định */
    }
  }, []);

  useEffect(() => {
    const doKichThuoc = () => setHep(window.innerWidth < 1024);
    doKichThuoc();
    window.addEventListener("resize", doKichThuoc);
    return () => window.removeEventListener("resize", doKichThuoc);
  }, []);

  const luuDoRong = useCallback((trai: number, phai: number) => {
    localStorage.setItem(KHOA, JSON.stringify({ trai, phai }));
  }, []);

  useEffect(() => {
    if (hep) return;

    function dichChuyen(e: MouseEvent) {
      if (!keo.current) return;
      // Chặn bôi đen văn bản trong lúc kéo — nếu không thì cả trang bị chọn.
      e.preventDefault();
      if (keo.current === "trai") {
        setRongTrai(Math.min(MAX, Math.max(MIN, e.clientX)));
      } else {
        setRongPhai(Math.min(MAX, Math.max(MIN, window.innerWidth - e.clientX)));
      }
    }
    function tha() {
      if (!keo.current) return;
      keo.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setRongTrai((t) => {
        setRongPhai((p) => {
          luuDoRong(t, p);
          return p;
        });
        return t;
      });
    }

    window.addEventListener("mousemove", dichChuyen);
    window.addEventListener("mouseup", tha);
    return () => {
      window.removeEventListener("mousemove", dichChuyen);
      window.removeEventListener("mouseup", tha);
    };
  }, [hep, luuDoRong]);

  function batDauKeo(ben: "trai" | "phai") {
    keo.current = ben;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  if (hep) {
    const noiDung = { nguon, hoi: hoiDap, xem: xemTaiLieu }[tab];
    return (
      <div className="flex h-full flex-col">
        <nav className="flex shrink-0 border-b border-vien bg-the" role="tablist">
          {(
            [
              ["nguon", t("cot.nguon")],
              ["hoi", t("cot.hoiThoai")],
              ["xem", t("cot.taiLieu")],
            ] as [Tab, string][]
          ).map(([ma, nhan]) => (
            <button
              key={ma}
              role="tab"
              aria-selected={tab === ma}
              onClick={() => setTab(ma)}
              className={`flex-1 px-4 py-3 text-sm font-medium ${
                tab === ma ? "border-b-2 border-nhan text-nhan" : "text-mo"
              }`}
            >
              {nhan}
            </button>
          ))}
        </nav>
        <div className="min-h-0 flex-1 overflow-y-auto">{noiDung}</div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <div style={{ width: rongTrai }} className="shrink-0 overflow-y-auto border-r border-vien bg-the">
        {nguon}
      </div>
      <ThanhKeo onMouseDown={() => batDauKeo("trai")} nhan={t("cot.keoCotNguon")} />

      {/* KHÔNG đặt `overflow-y-auto` ở đây: cột hội thoại tự cuộn phần tin nhắn
          và ghim ô soạn ở đáy. Thêm một tầng cuộn nữa chỉ cho ra hai thanh cuộn
          lồng nhau và một dải trống bên phải ô nhập. */}
      <div className="min-w-0 flex-1 overflow-hidden">{hoiDap}</div>

      <ThanhKeo onMouseDown={() => batDauKeo("phai")} nhan={t("cot.keoCotTaiLieu")} />
      <div style={{ width: rongPhai }} className="shrink-0 overflow-y-auto border-l border-vien bg-the">
        {xemTaiLieu}
      </div>
    </div>
  );
}

function ThanhKeo({ onMouseDown, nhan }: { onMouseDown: () => void; nhan: string }) {
  return (
    <div
      role="separator"
      aria-label={nhan}
      onMouseDown={onMouseDown}
      className="w-1 shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-nhan/40"
    />
  );
}
