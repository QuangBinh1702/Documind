"use client";

/**
 * Cột xem tài liệu — US-016 AC-5, US-014, US-015, US-017.
 *
 * Hai mức xem, và thứ tự giữa chúng là có chủ ý:
 *
 * 1. **Đoạn được trích dẫn** — mở ngay khi bấm một chip. Đây là câu trả lời cho
 *    "câu này dựa vào đâu", và nó phải tới trong một lần bấm.
 * 2. **Cả tài liệu** — mở khi người dùng muốn đọc phần xung quanh. PDF dựng
 *    bằng PDF.js kèm vùng tô sáng; ảnh hiện bản gốc cạnh chữ đọc được; tài liệu
 *    văn bản hiện toàn văn đã chuẩn hoá.
 *
 * Không mở thẳng mức 2: dựng một trang PDF tốn vài trăm mili giây và tải tệp
 * gốc tốn nhiều hơn thế, trong khi phần lớn lượt bấm chip chỉ cần đọc đúng đoạn
 * văn ấy.
 */

import { useEffect, useState } from "react";
import { type TrichDan, api, goiTho } from "@/lib/api";
import { type HopToaDo, XemPdf } from "@/components/XemPdf";

type ChiTiet = {
  chunk_id: number;
  content: string;
  page_no: number | null;
  heading_path: string | null;
  char_start: number;
  char_end: number;
  bbox: HopToaDo[] | null;
  source: { id: string; title: string; kind: string; pages: number | null };
};

type Muc = "doan" | "tai-lieu";

export function CotTaiLieu({
  nbId,
  trichDan,
}: {
  nbId: string;
  trichDan: TrichDan | null;
}) {
  const [chiTiet, setChiTiet] = useState<ChiTiet | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [dangTai, setDangTai] = useState(false);
  const [muc, setMuc] = useState<Muc>("doan");

  useEffect(() => {
    if (!trichDan) {
      setChiTiet(null);
      return;
    }
    let huy = false;
    setDangTai(true);
    setLoi(null);
    // Mỗi trích dẫn mới quay về mức "đoạn": người dùng vừa hỏi một câu khác,
    // giữ nguyên cả tài liệu của câu trước là giữ sai ngữ cảnh.
    setMuc("doan");

    api
      .trichDan(trichDan.chunk_id)
      .then((d) => {
        if (!huy) setChiTiet(d as ChiTiet);
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
      <div className="flex shrink-0 items-center gap-2 border-b border-vien px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-mo">
          {muc === "doan" ? "Đoạn được trích dẫn" : "Tài liệu"}
        </h2>
        {chiTiet && (
          <button
            onClick={() => setMuc((m) => (m === "doan" ? "tai-lieu" : "doan"))}
            className="ml-auto rounded-md border border-vien px-2 py-0.5 text-xs text-mo hover:border-nhan hover:text-nhan"
          >
            {muc === "doan" ? "Mở cả tài liệu" : "← Về đoạn trích"}
          </button>
        )}
      </div>

      {muc === "tai-lieu" && chiTiet ? (
        <div className="min-h-0 flex-1">
          <XemTaiLieu nbId={nbId} chiTiet={chiTiet} />
        </div>
      ) : (
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
            <KhungCho />
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
            </article>
          ) : null}
        </div>
      )}
    </div>
  );
}

/** Chọn cách hiển thị theo loại nguồn — US-017 AC-1, AC-2, AC-3. */
function XemTaiLieu({ nbId, chiTiet }: { nbId: string; chiTiet: ChiTiet }) {
  if (chiTiet.source.kind === "pdf") {
    return (
      <XemPdf
        nbId={nbId}
        sourceId={chiTiet.source.id}
        trang={chiTiet.page_no}
        hop={chiTiet.bbox ?? []}
      />
    );
  }
  if (chiTiet.source.kind === "image") {
    return <XemAnh nbId={nbId} chiTiet={chiTiet} />;
  }
  return <XemVanBan nbId={nbId} chiTiet={chiTiet} />;
}

/**
 * Ảnh gốc và chữ đọc được, cạnh nhau — AC-3.
 *
 * Cạnh nhau chứ không chỉ một trong hai, vì OCR tiếng Việt còn sai (xem
 * `docs/evidence/M3-ocr-tieng-viet.md`). Người đọc cần đối chiếu được với ảnh
 * gốc để biết chỗ nào tin được.
 */
function XemAnh({ nbId, chiTiet }: { nbId: string; chiTiet: ChiTiet }) {
  const url = useTepBlob(`/api/notebooks/${nbId}/sources/${chiTiet.source.id}/file`);

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
        Chữ đọc được từ ảnh
      </p>
      <pre className="mt-1.5 whitespace-pre-wrap rounded-md border border-vien bg-nen p-3 text-[13px] leading-relaxed">
        {chiTiet.content}
      </pre>
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
function XemVanBan({ nbId, chiTiet }: { nbId: string; chiTiet: ChiTiet }) {
  const [text, setText] = useState<string | null>(null);
  const [loi, setLoi] = useState(false);

  useEffect(() => {
    let huy = false;
    goiTho(`/api/notebooks/${nbId}/sources/${chiTiet.source.id}/text`)
      .then(async (r) => {
        if (!r.ok) throw new Error(String(r.status));
        const d = await r.json();
        if (!huy) setText(d.full_text as string);
      })
      .catch(() => {
        if (!huy) setLoi(true);
      });
    return () => {
      huy = true;
    };
  }, [nbId, chiTiet.source.id]);

  useEffect(() => {
    if (text) document.getElementById("doan-duoc-trich")?.scrollIntoView({ block: "center" });
  }, [text]);

  if (loi) return <p className="p-4 text-sm text-canh-bao">Không tải được nội dung tài liệu.</p>;
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
function useTepBlob(duong: string): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let huy = false;
    let hienTai: string | null = null;

    goiTho(duong)
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
  }, [duong]);

  return url;
}

function KhungCho() {
  return (
    <div className="space-y-2">
      <div className="h-4 w-2/3 animate-pulse rounded bg-vien" />
      <div className="h-3 w-1/3 animate-pulse rounded bg-vien" />
      <div className="mt-3 h-28 animate-pulse rounded-md bg-vien" />
    </div>
  );
}
