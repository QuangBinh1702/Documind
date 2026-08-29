"use client";

/**
 * Cột xem tài liệu — US-016 AC-5, US-014, US-015, US-017.
 *
 * Bấm một chip trích dẫn mở thẳng **tài liệu tại đúng chỗ được trích**: PDF
 * dựng bằng PDF.js kèm vùng tô sáng theo toạ độ, tài liệu văn bản hiện toàn văn
 * đã dựng định dạng với đoạn được tô, ảnh hiện bản gốc cạnh chữ đọc được.
 *
 * Không có nút chuyển sang "chỉ đoạn trích"
 * -----------------------------------------
 * Đã từng có, và nó là một lựa chọn giả. Người ta bấm chip để hỏi *"câu này lấy
 * ở đâu ra"*, và câu trả lời cho việc đó luôn là trang tài liệu chứ không phải
 * một khối chữ rời. Một nút chuyển chỉ bắt người dùng quyết định một việc mà
 * họ không có lý do gì để quyết định, và nó chiếm mất chỗ trên thanh tiêu đề
 * vốn đã hẹp của cột này.
 *
 * Mức "chỉ đoạn trích" vẫn còn, nhưng là **đường lùi tự động**: khi tệp gốc
 * không mở được — nguồn nạp bằng CLI không có bản lưu, hoặc tệp đã mất trên
 * kho — thì hiện nguyên văn đoạn trích kèm một dòng nói rõ vì sao. Đó là bậc 3
 * trong thang giảm cấp của US-015 AC-5, và nó phải tới mà không cần ai bấm gì.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { type TrichDan } from "@/lib/api";
import { type ChiTietTrichDan, type NguonXem } from "@/lib/nguonXem";
import { XemPdf } from "@/components/XemPdf";
import { Bt } from "@/components/BieuTuong";
import { useNgonNgu } from "@/components/NgonNguProvider";

export function CotTaiLieu({
  nguon,
  trichDan,
}: {
  nguon: NguonXem;
  trichDan: TrichDan | null;
}) {
  const [chiTiet, setChiTiet] = useState<ChiTietTrichDan | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [dangTai, setDangTai] = useState(false);
  const [khongMoDuoc, setKhongMoDuoc] = useState(false);
  const { t } = useNgonNgu();

  // Ổn định qua các lượt vẽ: trình xem giữ nó trong mảng phụ thuộc của hiệu
  // ứng tải tệp, nên một hàm mới mỗi lượt sẽ thành vòng lặp tải lại.
  const baoKhongMoDuoc = useCallback(() => setKhongMoDuoc(true), []);

  useEffect(() => {
    if (!trichDan) {
      setChiTiet(null);
      return;
    }
    let huy = false;
    setDangTai(true);
    setLoi(null);
    setKhongMoDuoc(false);

    nguon
      .trichDan(trichDan.chunk_id)
      .then((d) => {
        if (!huy) setChiTiet(d);
      })
      .catch(() => {
        if (!huy) setLoi(t("xem.khongTaiDuocTrichDan"));
      })
      .finally(() => {
        if (!huy) setDangTai(false);
      });
    return () => {
      huy = true;
    };
  }, [nguon, trichDan]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center border-b border-vien px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-mo">
          {t("xem.doanTrichDan")}
        </h2>
      </div>

      {!trichDan ? (
        <div className="px-4 py-4">
          <div className="rounded-lg border border-dashed border-vien px-4 py-8 text-center">
            <Bt.ngam size={20} className="mx-auto text-mo opacity-60" />
            <p className="mt-2 text-sm font-medium">{t("xem.chuaChon")}</p>
            <p className="mt-1 text-xs text-mo">{t("xem.huongDanChip")}</p>
          </div>
        </div>
      ) : dangTai ? (
        <KhungCho />
      ) : loi ? (
        <p className="px-4 py-4 text-sm text-canh-bao">{loi}</p>
      ) : chiTiet ? (
        <>
          <TheNguon chiTiet={chiTiet} />
          <div className="min-h-0 flex-1">
            {khongMoDuoc ? (
              <DoanTrich chiTiet={chiTiet} />
            ) : (
              <XemTaiLieu
                nguon={nguon}
                chiTiet={chiTiet}
                onKhongMoDuoc={baoKhongMoDuoc}
              />
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

/**
 * Tài liệu nào, trang nào, mục nào.
 *
 * Đây là câu trả lời ngắn cho *"câu này lấy ở đâu ra"*, và nó phải đọc được
 * ngay cả khi tệp gốc còn đang tải.
 */
function TheNguon({ chiTiet }: { chiTiet: ChiTietTrichDan }) {
  const { t } = useNgonNgu();
  const Icon = chiTiet.source.kind === "image" ? Bt.anh : Bt.tep;

  return (
    <div className="shrink-0 border-b border-vien bg-the px-4 py-3">
      <div className="flex items-start gap-2">
        <Icon size={14} className="mt-[3px] shrink-0 text-mo" />
        <div className="min-w-0">
          <p
            className="text-sm font-medium leading-snug"
            title={chiTiet.source.title}
          >
            {chiTiet.source.title}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-mo">
            <span>
              {chiTiet.page_no
                ? t("xem.trangSo", { so: chiTiet.page_no })
                : t("xem.khongRoTrang")}
              {chiTiet.source.pages ? ` / ${chiTiet.source.pages}` : ""}
            </span>
            {chiTiet.heading_path && (
              <>
                <span aria-hidden="true" className="opacity-50">
                  ·
                </span>
                <span className="truncate" title={chiTiet.heading_path}>
                  {chiTiet.heading_path}
                </span>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * Bậc 3 của thang giảm cấp US-015 AC-5 — chỉ nguyên văn đoạn được trích.
 *
 * Chỉ tới khi tệp gốc không mở được, và nói thẳng lý do: một khối chữ hiện ra
 * mà không giải thích gì sẽ bị đọc là giao diện hỏng.
 */
function DoanTrich({ chiTiet }: { chiTiet: ChiTietTrichDan }) {
  const { t } = useNgonNgu();
  return (
    <div className="h-full overflow-y-auto px-4 py-4">
      <p className="mb-3 rounded-md border border-vien bg-nen px-3 py-2 text-xs text-mo">
        {t("xem.khongMoDuocDungDoan")}
      </p>
      <Md text={chiTiet.content} />
    </div>
  );
}

/** Chọn cách hiển thị theo loại nguồn — US-017 AC-1, AC-2, AC-3. */
function XemTaiLieu({
  nguon,
  chiTiet,
  onKhongMoDuoc,
}: {
  nguon: NguonXem;
  chiTiet: ChiTietTrichDan;
  onKhongMoDuoc: () => void;
}) {
  if (chiTiet.source.kind === "pdf") {
    return (
      <XemPdf
        nguon={nguon}
        sourceId={chiTiet.source.id}
        trang={chiTiet.page_no}
        hop={chiTiet.bbox ?? []}
        onKhongMoDuoc={onKhongMoDuoc}
      />
    );
  }
  if (chiTiet.source.kind === "image") {
    return <XemAnh nguon={nguon} chiTiet={chiTiet} />;
  }
  return (
    <XemVanBan nguon={nguon} chiTiet={chiTiet} onKhongMoDuoc={onKhongMoDuoc} />
  );
}

/**
 * Ảnh gốc và chữ đọc được, cạnh nhau — AC-3.
 *
 * Cạnh nhau chứ không chỉ một trong hai, vì OCR tiếng Việt còn sai (xem
 * `docs/evidence/M3-ocr-tieng-viet.md`). Người đọc cần đối chiếu được với ảnh
 * gốc để biết chỗ nào tin được.
 */
function XemAnh({ nguon, chiTiet }: { nguon: NguonXem; chiTiet: ChiTietTrichDan }) {
  const url = useTepBlob(nguon, chiTiet.source.id);
  const { t } = useNgonNgu();

  return (
    <div className="h-full overflow-y-auto p-4">
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt={chiTiet.source.title}
          className="w-full rounded-md border border-vien bg-white"
        />
      ) : (
        <div className="h-48 animate-pulse rounded-md bg-vien" />
      )}
      <p className="mt-4 text-xs font-semibold uppercase tracking-wider text-mo">
        {t("xem.chuTuAnh")}
      </p>
      <div className="mt-2 khoi-to-sang">
        <Md text={chiTiet.content} />
      </div>
    </div>
  );
}

/**
 * Toàn văn tài liệu, tô sáng đúng đoạn được trích — AC-2.
 *
 * Hai điều đáng nói.
 *
 * **Dựng định dạng, không hiện chữ thô.** AC-2 đòi tài liệu DOCX/TXT/MD hiện ở
 * dạng Markdown *có định dạng*. Bản trước đổ toàn văn vào một thẻ `<pre>` phông
 * đơn cách, nên `## Bước 6` và `# Checklist` nằm nguyên trên màn hình dưới dạng
 * dấu thăng, và một tài liệu hướng dẫn bình thường đọc như tệp cấu hình.
 *
 * **Cắt theo `char_start`/`char_end`, không đi tìm lại chuỗi.** Đó là toàn bộ
 * giá trị của bất biến INV-1: offset dựng lên lúc trích xuất và dùng lại được
 * nguyên vẹn ở đây. Tìm lại bằng `indexOf` sẽ trỏ nhầm ngay khi một đoạn xuất
 * hiện hai lần trong tài liệu.
 *
 * Ranh giới tô sáng được **nới ra tới đầu và cuối dòng** trước khi vẽ. Việc này
 * chỉ ảnh hưởng tới phần hiển thị, không đụng tới offset đã lưu, và nó cần
 * thiết vì ba mảnh được dựng Markdown riêng: cắt giữa dòng sẽ chẻ đôi một tiêu
 * đề hoặc một dấu `**`, và mảnh sau sẽ hiện ra ký hiệu Markdown thô.
 */
function XemVanBan({
  nguon,
  chiTiet,
  onKhongMoDuoc,
}: {
  nguon: NguonXem;
  chiTiet: ChiTietTrichDan;
  onKhongMoDuoc: () => void;
}) {
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    let huy = false;
    nguon
      .vanBan(chiTiet.source.id)
      .then((d) => {
        if (!huy) setText(d.full_text);
      })
      .catch(() => {
        if (!huy) onKhongMoDuoc();
      });
    return () => {
      huy = true;
    };
  }, [nguon, chiTiet.source.id, onKhongMoDuoc]);

  const phan = useMemo(() => {
    if (text === null) return null;
    const dau =
      chiTiet.char_start === 0
        ? 0
        : text.lastIndexOf("\n", chiTiet.char_start - 1) + 1;
    const sauDo = text.indexOf("\n", chiTiet.char_end);
    const cuoi = sauDo === -1 ? text.length : sauDo;
    return {
      truoc: text.slice(0, dau),
      giua: text.slice(dau, cuoi),
      sau: text.slice(cuoi),
    };
  }, [text, chiTiet.char_start, chiTiet.char_end]);

  useEffect(() => {
    if (phan) {
      document
        .getElementById("doan-duoc-trich")
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [phan]);

  if (phan === null) {
    return (
      <div className="space-y-2.5 p-4">
        {Array.from({ length: 10 }, (_, i) => (
          <div
            key={i}
            className="h-3 animate-pulse rounded bg-vien"
            style={{ width: `${70 + ((i * 13) % 30)}%` }}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-4 py-4">
      <Md text={phan.truoc} />
      <div id="doan-duoc-trich" className="khoi-to-sang">
        <Md text={phan.giua} />
      </div>
      <Md text={phan.sau} />
    </div>
  );
}

/**
 * Một mảnh Markdown của tài liệu nguồn.
 *
 * Không có `rehype-raw`, nên HTML thô nằm trong tài liệu người dùng tải lên
 * được hiển thị như chữ chứ không chạy — cùng lý do với `VanBanTraLoi`.
 */
function Md({ text }: { text: string }) {
  if (!text.trim()) return null;
  return (
    <div className="prose-tra-loi prose-tai-lieu">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

/**
 * Tải một tệp cần xác thực rồi trả về URL blob dùng được cho `<img>`.
 *
 * Đặt thẳng đường API vào `src` thì trình duyệt tự gửi request mà không kèm
 * `Authorization`, và ảnh trả về 401.
 */
function useTepBlob(nguon: NguonXem, sourceId: string): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let huy = false;
    let hienTai: string | null = null;

    nguon
      .tep(sourceId)
      .then(async (r) => {
        if (!r.ok) return;
        const blob = await r.blob();
        if (huy) return;
        hienTai = URL.createObjectURL(blob);
        setUrl(hienTai);
      })
      .catch(() => {
        /* hiện khung xương mãi còn hơn hiện một ảnh vỡ */
      });

    return () => {
      huy = true;
      if (hienTai) URL.revokeObjectURL(hienTai);
    };
  }, [nguon, sourceId]);

  return url;
}

function KhungCho() {
  return (
    <div className="space-y-2 px-4 py-4">
      <div className="h-4 w-2/3 animate-pulse rounded bg-vien" />
      <div className="h-3 w-1/3 animate-pulse rounded bg-vien" />
      <div className="mt-3 h-64 animate-pulse rounded-md bg-vien" />
    </div>
  );
}
