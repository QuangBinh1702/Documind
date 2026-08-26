"use client";

/**
 * Câu trả lời dạng Markdown, marker `[n]` thành chip bấm được — US-014 AC-2.
 *
 * Mô hình trả về Markdown (danh sách, in đậm, bảng) và bản đầu tiên hiện nó
 * như chữ thô kèm `whitespace-pre-wrap`, nên dấu `**` và `-` nằm nguyên trên
 * màn hình. `react-markdown` dựng cây React từ Markdown và **không** chèn HTML
 * thô (không có `rehype-raw`), nên nội dung do mô hình sinh không trở thành
 * kênh XSS.
 *
 * Chip: `react-markdown` không cho thay node văn bản, nên marker được đổi
 * thành liên kết `[n](#cite-n)` trước khi parse, và thẻ `a` trỏ vào `#cite-`
 * được vẽ thành chip. Marker trong khối mã để nguyên.
 */

import { memo, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { TrichDan } from "@/lib/api";
import { useNgonNgu } from "@/components/NgonNguProvider";

const MARKER = /\[(\d{1,3})\](?!\()/g;

/** Đổi `[n]` thành liên kết nội bộ, bỏ qua khối mã ``` và mã nội dòng. */
function danhDauMarker(text: string): string {
  const phan = text.split(/(```[\s\S]*?```|`[^`\n]*`)/g);
  return phan
    .map((p, i) => (i % 2 === 1 ? p : p.replace(MARKER, "[$1](#cite-$1)")))
    .join("");
}

export const VanBanTraLoi = memo(function VanBanTraLoi({
  text,
  trichDan,
  markerChet,
  onChon,
}: {
  text: string;
  trichDan: Record<number, TrichDan>;
  markerChet?: Set<number>;
  onChon: (t: TrichDan) => void;
}) {
  const { t } = useNgonNgu();
  const noiDung = useMemo(() => danhDauMarker(text), [text]);

  const components = useMemo<Components>(
    () => ({
      a: ({ href, children }) => {
        const m = href && /^#cite-(\d+)$/.exec(href);
        if (!m) {
          // Liên kết thật (hiếm — mô hình không được bảo chèn) mở tab mới.
          return (
            <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
              {children}
            </a>
          );
        }
        const so = Number(m[1]);
        const cite = trichDan[so];
        const daXoa = markerChet?.has(so) ?? false;
        return (
          <button
            type="button"
            disabled={!cite}
            onClick={() => cite && onChon(cite)}
            className={`chip${cite ? "" : " chip-chet"}`}
            title={
              cite
                ? cite.heading_path
                  ? `${cite.heading_path}${cite.page ? ` · ${t("xem.trangSo", { so: cite.page })}` : ""}`
                  : t("chip.xemDoanGoc")
                : daXoa
                  ? t("chip.nguonDaXoa")
                  : t("chip.khongTonTai")
            }
          >
            {so}
          </button>
        );
      },
    }),
    [trichDan, markerChet, onChon, t],
  );

  return (
    <div className="prose-tra-loi">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {noiDung}
      </ReactMarkdown>
    </div>
  );
});
