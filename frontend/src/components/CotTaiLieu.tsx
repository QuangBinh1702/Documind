"use client";

/**
 * Cột xem tài liệu — US-016 AC-5, US-014, US-015, US-017.
 *
 * Bấm một chip trích dẫn mở thẳng **tài liệu tại đúng chỗ được trích**: PDF
 * dựng bằng PDF.js kèm vùng tô sáng theo toạ độ, tài liệu văn bản hiện toàn văn
 * với đoạn được tô, ảnh hiện bản gốc cạnh chữ đọc được.
 *
 * Vì sao mặc định là cả tài liệu chứ không phải mỗi đoạn văn
 * -----------------------------------------------------------
 * Bản trước mở ở mức "đoạn": một khối chữ trần, và muốn thấy nó nằm ở đâu trong
 * tài liệu thì phải bấm thêm một nút nữa. Cách ấy rẻ hơn — dựng một trang PDF
 * tốn vài trăm mili giây và tải tệp gốc tốn nhiều hơn thế — nhưng nó trả lời
 * sai câu hỏi. Người ta bấm chip để hỏi *"câu này lấy ở đâu ra"*, và một đoạn
 * văn tách khỏi trang giấy chứa nó thì không trả lời được câu đó: không thấy
 * tiêu đề mục, không thấy bảng bên cạnh, không kiểm chứng được gì. Đó cũng
 * đúng là bậc 1 trong thang giảm cấp của US-015 AC-5, và hạ tầng cho nó đã
 * sẵn sàng từ M2.
 *
 * Mức "chỉ đoạn trích" vẫn còn, ngay cạnh đó, cho lúc mạng chậm hoặc tệp gốc
 * không còn trên máy chủ (nguồn nạp bằng CLI). Đó là bậc 3 của cùng thang ấy.
 */

import { useEffect, useState } from "react";
import { type TrichDan } from "@/lib/api";
import { type ChiTietTrichDan, type NguonXem } from "@/lib/nguonXem";
import { XemPdf } from "@/components/XemPdf";
import { Bt } from "@/components/BieuTuong";
import { useNgonNgu } from "@/components/NgonNguProvider";

type Muc = "doan" | "tai-lieu";

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
  const [muc, setMuc] = useState<Muc>("tai-lieu");
  const { t } = useNgonNgu();

  useEffect(() => {
    if (!trichDan) {
      setChiTiet(null);
      return;
    }
    let huy = false;
    setDangTai(true);
    setLoi(null);
    // Mỗi trích dẫn mới quay về mức mặc định: người dùng vừa hỏi một câu khác,
    // giữ nguyên lựa chọn của câu trước là giữ sai ngữ cảnh.
    setMuc("tai-lieu");

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
      <div className="flex shrink-0 items-center gap-2 border-b border-vien px-4 py-2.5">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-mo">
          {t("xem.doanTrichDan")}
        </h2>
        {chiTiet && <ChonMuc muc={muc} doi={setMuc} />}
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
            {muc === "tai-lieu" ? (
              <XemTaiLieu nguon={nguon} chiTiet={chiTiet} />
            ) : (
              <DoanTrich chiTiet={chiTiet} />
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

/**
 * Chuyển giữa hai mức xem.
 *
 * Hai nút cạnh nhau chứ không phải một nút bật/tắt: nút bật/tắt bắt người đọc
 * suy ra mình đang ở đâu từ nhãn của thứ mình sắp đi tới, và bản trước đúng là
 * đã sai kiểu đó — nhãn *"Mở cả tài liệu"* nằm ngay cạnh tiêu đề *"Đoạn được
 * trích dẫn"*, không có gì đánh dấu mức hiện tại.
 */
function ChonMuc({ muc, doi }: { muc: Muc; doi: (m: Muc) => void }) {
  const { t } = useNgonNgu();
  const nut = (m: Muc, icon: React.ReactNode, nhan: string) => (
    <button
      onClick={() => doi(m)}
      aria-pressed={muc === m}
      title={nhan}
      className={`flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors ${
        muc === m
          ? "bg-nen text-chu shadow-sm"
          : "text-mo hover:text-chu"
      }`}
    >
      {icon}
      <span className="hidden xl:inline">{nhan}</span>
    </button>
  );

  return (
    <div className="ml-auto flex rounded-md border border-vien bg-the p-0.5">
      {nut("tai-lieu", <Bt.taiLieu size={13} />, t("xem.trongTaiLieu"))}
      {nut("doan", <Bt.chuNghia size={13} />, t("xem.chiDoanTrich"))}
    </div>
  );
}

/**
 * Tài liệu nào, trang nào, mục nào — luôn hiện, ở cả hai mức xem.
 *
 * Đây là câu trả lời ngắn cho *"câu này lấy ở đâu ra"*, và nó phải đọc được
 * ngay cả khi tệp gốc còn đang tải.
 */
function TheNguon({ chiTiet }: { chiTiet: ChiTietTrichDan }) {
  const { t } = useNgonNgu();
  const Icon = chiTiet.source.kind === "image" ? Bt.anh : Bt.tep;

  return (
    <div className="shrink-0 border-b border-vien bg-the px-4 py-2.5">
      <div className="flex items-start gap-2">
        <Icon size={14} className="mt-0.5 shrink-0 text-mo" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium" title={chiTiet.source.title}>
            {chiTiet.source.title}
          </p>
          <p className="mt-0.5 text-xs text-mo">
            {chiTiet.page_no
              ? t("xem.trangSo", { so: chiTiet.page_no })
              : t("xem.khongRoTrang")}
            {chiTiet.source.pages ? ` / ${chiTiet.source.pages}` : ""}
          </p>
        </div>
      </div>
      {chiTiet.heading_path && (
        <p
          className="mt-1.5 truncate text-xs text-mo"
          title={chiTiet.heading_path}
        >
          {chiTiet.heading_path}
        </p>
      )}
    </div>
  );
}

/** Bậc 3 của thang giảm cấp US-015 AC-5 — chỉ nguyên văn đoạn được trích. */
function DoanTrich({ chiTiet }: { chiTiet: ChiTietTrichDan }) {
  return (
    <div className="h-full overflow-y-auto px-4 py-4">
      <blockquote className="border-l-2 border-nhan pl-3 text-[13px] leading-relaxed whitespace-pre-wrap">
        {chiTiet.content}
      </blockquote>
    </div>
  );
}

/** Chọn cách hiển thị theo loại nguồn — US-017 AC-1, AC-2, AC-3. */
function XemTaiLieu({
  nguon,
  chiTiet,
}: {
  nguon: NguonXem;
  chiTiet: ChiTietTrichDan;
}) {
  if (chiTiet.source.kind === "pdf") {
    return (
      <XemPdf
        nguon={nguon}
        sourceId={chiTiet.source.id}
        trang={chiTiet.page_no}
        hop={chiTiet.bbox ?? []}
      />
    );
  }
  if (chiTiet.source.kind === "image") {
    return <XemAnh nguon={nguon} chiTiet={chiTiet} />;
  }
  return <XemVanBan nguon={nguon} chiTiet={chiTiet} />;
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
    <div className="h-full overflow-y-auto p-3">
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
      <p className="mt-3 text-xs font-semibold uppercase tracking-wider text-mo">
        {t("xem.chuTuAnh")}
      </p>
      <blockquote className="mt-1.5 border-l-2 border-nhan pl-3 text-[13px] leading-relaxed whitespace-pre-wrap">
        {chiTiet.content}
      </blockquote>
    </div>
  );
}

/**
 * Toàn văn tài liệu, tô sáng đúng đoạn được trích — AC-2.
 *
 * Cắt theo `char_start`/`char_end` chứ không đi tìm lại chuỗi trong văn bản.
 * Đó là toàn bộ giá trị của bất biến INV-1: offset dựng lên lúc trích xuất và
 * dùng lại được nguyên vẹn ở đây. Tìm lại bằng `indexOf` sẽ trỏ nhầm ngay khi
 * một đoạn xuất hiện hai lần trong tài liệu.
 */
function XemVanBan({ nguon, chiTiet }: { nguon: NguonXem; chiTiet: ChiTietTrichDan }) {
  const [text, setText] = useState<string | null>(null);
  const [loi, setLoi] = useState(false);
  const { t } = useNgonNgu();

  useEffect(() => {
    let huy = false;
    nguon
      .vanBan(chiTiet.source.id)
      .then((d) => {
        if (!huy) setText(d.full_text);
      })
      .catch(() => {
        if (!huy) setLoi(true);
      });
    return () => {
      huy = true;
    };
  }, [nguon, chiTiet.source.id]);

  useEffect(() => {
    if (text) {
      document
        .getElementById("doan-duoc-trich")
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [text]);

  if (loi)
    return <p className="p-4 text-sm text-canh-bao">{t("xem.khongTaiDuocNoiDung")}</p>;
  if (text === null) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="h-3 animate-pulse rounded bg-vien" />
        ))}
      </div>
    );
  }

  const truoc = text.slice(0, chiTiet.char_start);
  const giua = text.slice(chiTiet.char_start, chiTiet.char_end);
  const sau = text.slice(chiTiet.char_end);

  return (
    <div className="h-full overflow-y-auto p-4">
      <pre className="whitespace-pre-wrap text-[13px] leading-relaxed">
        {truoc}
        <mark id="doan-duoc-trich" className="to-sang">
          {giua}
        </mark>
        {sau}
      </pre>
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
