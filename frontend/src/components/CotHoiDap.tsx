"use client";

/**
 * Cột hội thoại — US-012, US-013, US-014.
 *
 * Câu trả lời hiện dần theo từng mẩu, và marker `[n]` biến thành chip bấm được.
 * Marker mà không có trích dẫn tương ứng thì hiện mờ và không bấm được: mô hình
 * đôi khi bịa ra số đoạn không tồn tại, và một chip bấm vào không đi đâu cả làm
 * người dùng mất niềm tin vào toàn bộ tính năng trích dẫn.
 */

import { useEffect, useRef, useState } from "react";
import type { TrichDan } from "@/lib/api";
import { hoi, type SuKien } from "@/lib/stream";

type NgoaiMay = { model: string; keCaTaiLieu: boolean };

type Luot = {
  cauHoi: string;
  traLoi: string;
  trichDan: Record<number, TrichDan>;
  tuChoi: boolean;
  ngoaiMay: NgoaiMay | null;
  trangThai: string | null;
  xong: boolean;
  loi: string | null;
};

const NHAN_BUOC: Record<string, string> = {
  retrieving: "đang tìm trong tài liệu",
  reranking: "đang xếp hạng đoạn liên quan",
  generating: "đang viết câu trả lời",
  verifying: "đang kiểm định",
  regenerating: "đang viết lại",
};

export function CotHoiDap({
  nbId,
  sanSang,
  onChonTrichDan,
}: {
  nbId: string;
  sanSang: boolean;
  onChonTrichDan: (t: TrichDan) => void;
}) {
  const [luot, setLuot] = useState<Luot[]>([]);
  const [cauHoi, setCauHoi] = useState("");
  const [dangHoi, setDangHoi] = useState(false);

  // Cảnh báo quyền riêng tư chỉ hiện MỘT LẦN cho cả cuộc hội thoại.
  //
  // Lặp lại ở mọi câu trả lời thì sau ba câu người dùng không đọc nó nữa —
  // và một cảnh báo không ai đọc thì không còn là cảnh báo. `SPEC-REVIEW.md`
  // §A.4 cũng chỉ yêu cầu báo một lần.
  const [daBaoNgoaiMay, setDaBaoNgoaiMay] = useState(false);
  const cuoiRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    cuoiRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [luot]);

  async function gui(e: React.FormEvent) {
    e.preventDefault();
    const q = cauHoi.trim();
    if (!q || dangHoi) return;

    setCauHoi("");
    setDangHoi(true);
    const chiSo = luot.length;
    setLuot((cu) => [
      ...cu,
      {
        cauHoi: q,
        traLoi: "",
        trichDan: {},
        tuChoi: false,
        ngoaiMay: null,
        trangThai: null,
        xong: false,
        loi: null,
      },
    ]);

    const capNhat = (sua: (l: Luot) => Luot) =>
      setLuot((cu) => cu.map((l, i) => (i === chiSo ? sua(l) : l)));

    await hoi({ question: q, notebook_id: nbId }, (e: SuKien) => {
      switch (e.type) {
        case "external_call":
          // Máy chủ chỉ phát sự kiện này NGAY TRƯỚC lượt gọi thật sự gửi dữ
          // liệu đi, nên nó không bao giờ hiện nhầm ở đường từ chối — đường đó
          // không gọi mô hình.
          setDaBaoNgoaiMay((cu) => {
            if (cu) return cu; // đã báo rồi thì thôi, mỗi cuộc một lần
            capNhat((l) => ({
              ...l,
              ngoaiMay: {
                model: String(e.model),
                keCaTaiLieu: e.includes_documents !== false,
              },
            }));
            return true;
          });
          break;
        case "status":
          capNhat((l) => ({ ...l, trangThai: NHAN_BUOC[String(e.stage)] ?? null }));
          break;
        case "token":
          capNhat((l) => ({ ...l, traLoi: l.traLoi + String(e.text) }));
          break;
        case "replace":
          // Bản sinh lại thay thế toàn bộ; giao diện không rút lại được thứ đã
          // hiện nên phải vẽ lại từ đầu.
          capNhat((l) => ({ ...l, traLoi: String(e.text) }));
          break;
        case "citation":
          capNhat((l) => ({
            ...l,
            trichDan: { ...l.trichDan, [Number(e.marker)]: e as unknown as TrichDan },
          }));
          break;
        case "no_answer":
          capNhat((l) => ({ ...l, tuChoi: true }));
          break;
        case "error":
          capNhat((l) => ({ ...l, loi: String(e.message), xong: true }));
          break;
        case "done":
          capNhat((l) => ({ ...l, xong: true, trangThai: null }));
          break;
      }
    });

    setDangHoi(false);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        {luot.length === 0 && (
          <div className="mx-auto max-w-[68ch] rounded-lg border border-dashed border-vien px-5 py-10 text-center">
            <p className="font-medium">
              {sanSang ? "Hỏi gì đó về tài liệu của bạn" : "Chưa có tài liệu nào sẵn sàng"}
            </p>
            <p className="mt-1 text-sm text-mo">
              {sanSang
                ? "Mỗi khẳng định trong câu trả lời sẽ kèm số đoạn. Bấm vào số đó để đọc đúng đoạn văn gốc."
                : "Tải một tệp lên ở cột bên trái. Tài liệu cần được xử lý xong trước khi hỏi."}
            </p>
          </div>
        )}

        <div className="mx-auto max-w-[68ch] space-y-7">
          {luot.map((l, i) => (
            <div key={i}>
              <p className="text-sm text-mo">
                <b className="font-semibold text-chu">Bạn:</b> {l.cauHoi}
              </p>

              {l.ngoaiMay && (
                <p className="mt-2 text-xs text-canh-bao">
                  {l.ngoaiMay.keCaTaiLieu
                    ? `Chế độ này gửi câu hỏi và các đoạn tài liệu được chọn tới ${l.ngoaiMay.model}.`
                    : `Chế độ này gửi câu hỏi tới ${l.ngoaiMay.model}. Lần này không có đoạn tài liệu nào được gửi đi.`}{" "}
                  Chuyển sang Privacy Mode để không có gì rời khỏi máy.
                </p>
              )}

              <div
                className={`mt-2 whitespace-pre-wrap rounded-xl border px-4 py-3.5 ${
                  l.loi
                    ? "border-canh-bao bg-canh-bao-nen"
                    : l.tuChoi
                      ? "border-dashed border-vien text-mo"
                      : "border-vien bg-the"
                }`}
              >
                {l.loi ? (
                  l.loi
                ) : l.traLoi ? (
                  <VanBanCoChip
                    text={l.traLoi}
                    trichDan={l.trichDan}
                    onChon={onChonTrichDan}
                  />
                ) : (
                  <span className="text-sm italic text-mo">
                    {l.trangThai ?? "đang xử lý"}…
                  </span>
                )}
              </div>

              {l.xong && !l.loi && l.trangThai === null && Object.keys(l.trichDan).length > 0 && (
                <p className="mt-2 text-xs text-mo">
                  {Object.keys(l.trichDan).length} trích dẫn — bấm số để xem đoạn gốc
                </p>
              )}
            </div>
          ))}
          <div ref={cuoiRef} />
        </div>
      </div>

      <form onSubmit={gui} className="shrink-0 border-t border-vien px-6 py-4">
        <div className="mx-auto flex max-w-[68ch] gap-2">
          <input
            value={cauHoi}
            onChange={(e) => setCauHoi(e.target.value)}
            disabled={dangHoi}
            placeholder={sanSang ? "Hỏi gì đó về tài liệu…" : "Chưa có tài liệu sẵn sàng"}
            className="flex-1 rounded-md border border-vien bg-the px-3 py-2 outline-none focus:border-nhan disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={!cauHoi.trim() || dangHoi}
            className="rounded-md bg-nhan px-5 py-2 font-medium text-white disabled:opacity-45"
          >
            {dangHoi ? "…" : "Hỏi"}
          </button>
        </div>
      </form>
    </div>
  );
}

/** Biến `[n]` thành chip bấm được — US-014 AC-2. */
function VanBanCoChip({
  text,
  trichDan,
  onChon,
}: {
  text: string;
  trichDan: Record<number, TrichDan>;
  onChon: (t: TrichDan) => void;
}) {
  const phan = text.split(/(\[\d{1,2}\])/g);
  return (
    <>
      {phan.map((p, i) => {
        const khop = /^\[(\d{1,2})\]$/.exec(p);
        if (!khop) return <span key={i}>{p}</span>;

        const so = Number(khop[1]);
        const t = trichDan[so];
        return (
          <button
            key={i}
            type="button"
            disabled={!t}
            onClick={() => t && onChon(t)}
            className={`chip${t ? "" : " chip-chet"}`}
            title={t ? "Xem đoạn gốc" : "Trích dẫn không tồn tại"}
          >
            {so}
          </button>
        );
      })}
    </>
  );
}
