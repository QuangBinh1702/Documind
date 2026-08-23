"use client";

/**
 * Cột xem tài liệu — US-016 AC-5, US-014.
 *
 * Bấm một chip trích dẫn thì cột này hiện đúng đoạn văn gốc: tên tài liệu, số
 * trang, đường dẫn tiêu đề, và toàn văn đoạn đó. Đây là chỗ lời hứa "kiểm chứng
 * được" của cả hệ thống được thực hiện — người dùng nhìn thấy nguyên văn thay
 * vì phải tin.
 *
 * Chưa chọn gì thì hiện hướng dẫn, không phải khoảng trắng (AC-5).
 */

import { useEffect, useState } from "react";
import { type TrichDan, api } from "@/lib/api";

type ChiTiet = {
  chunk_id: number;
  content: string;
  page_no: number | null;
  heading_path: string | null;
  char_start: number;
  char_end: number;
  source: { id: string; title: string };
};

export function CotTaiLieu({ trichDan }: { trichDan: TrichDan | null }) {
  const [chiTiet, setChiTiet] = useState<ChiTiet | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [dangTai, setDangTai] = useState(false);

  useEffect(() => {
    if (!trichDan) {
      setChiTiet(null);
      return;
    }
    let huy = false;
    setDangTai(true);
    setLoi(null);
    api
      .trichDan(trichDan.chunk_id)
      .then((d) => {
        if (!huy) setChiTiet(d);
      })
      .catch(() => {
        if (!huy) setLoi("Không tải được đoạn trích dẫn. Nguồn có thể đã bị xoá.");
      })
      .finally(() => {
        if (!huy) setDangTai(false);
      });
    return () => {
      huy = true;
    };
  }, [trichDan]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-vien px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-mo">
          Đoạn được trích dẫn
        </h2>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {!trichDan ? (
          <div className="rounded-lg border border-dashed border-vien px-4 py-8 text-center">
            <p className="text-sm font-medium">Chưa chọn trích dẫn nào</p>
            <p className="mt-1 text-xs text-mo">
              Mỗi khẳng định trong câu trả lời kèm một số như{" "}
              <span className="chip">1</span>. Bấm vào số đó để đọc đúng đoạn văn
              mà câu trả lời dựa vào.
            </p>
          </div>
        ) : dangTai ? (
          <p className="text-sm text-mo">Đang tải…</p>
        ) : loi ? (
          <p className="text-sm text-canh-bao">{loi}</p>
        ) : chiTiet ? (
          <article>
            <p className="text-sm font-semibold">{chiTiet.source.title}</p>
            <p className="mt-0.5 text-xs text-mo">
              {chiTiet.page_no ? `Trang ${chiTiet.page_no}` : "Không rõ trang"}
              {chiTiet.heading_path ? ` · ${chiTiet.heading_path}` : ""}
            </p>

            <pre className="mt-3 whitespace-pre-wrap rounded-md border border-vien bg-nen p-3 text-[13px] leading-relaxed">
              {chiTiet.content}
            </pre>

            {/* Toạ độ ký tự là cầu nối tới tô sáng theo vị trí trên trang
                (US-015). Hiện ra để kiểm chứng được rằng trích dẫn trỏ vào một
                khoảng cụ thể chứ không phải cả tài liệu. */}
            <p className="mt-2 text-xs text-mo">
              ký tự {chiTiet.char_start}–{chiTiet.char_end}
            </p>
          </article>
        ) : null}
      </div>
    </div>
  );
}
