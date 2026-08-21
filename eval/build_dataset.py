"""Dựng bộ câu hỏi có nhãn — US-044.

Vì sao sinh câu hỏi TỪ đoạn văn, không phải đi tìm đáp án
---------------------------------------------------------
Cách hiển nhiên là soạn câu hỏi trước rồi đi tìm đoạn chứa đáp án. Cách đó có
một lỗ hổng: người đi tìm cũng chính là người quyết định "đoạn nào là đúng", và
nếu bộ truy xuất của hệ thống được dùng để tìm thì bộ đánh giá đang tự chấm
chính nó.

Ở đây làm ngược lại (US-044 AC-6): lấy một đoạn ra trước, bảo mô hình đặt câu
hỏi mà **đoạn đó** trả lời được. Ground truth khi ấy đúng theo **cấu tạo**, không
phải theo phán đoán. Không đường truy xuất nào tham gia vào việc dựng nhãn.

Neo nhãn bằng khoảng ký tự, không bằng `chunk_id`
--------------------------------------------------
`chunk_id` là khoá tự tăng, đổi mỗi lần nạp lại. Nếu bộ test neo vào nó thì chỉ
cần đổi `CHUNK_TOKENS` là toàn bộ nhãn mất giá trị. Nhãn ở đây neo vào
`(tệp nguồn, char_start, char_end)` — toạ độ trên văn bản gốc, không đổi theo
cách chia đoạn. Lúc chấm, một đoạn được tính là trúng khi nó **chồng lấn** khoảng
đó.

Câu hỏi ngoài phạm vi phải được kiểm chứng bằng NỘI DUNG, không bằng ĐIỂM
--------------------------------------------------------------------------
30 câu ở AC-4 dùng để hiệu chỉnh τ. Một câu tưởng là ngoài phạm vi mà thật ra có
đáp án trong tài liệu sẽ bị tính là "từ chối đúng" trong khi hệ thống lẽ ra phải
trả lời — và nó đẩy τ tối ưu lệch đi. Nên phải kiểm chứng.

Cách hiển nhiên là loại câu nào có điểm rerank cao. **Cách đó sai**, và sai theo
kiểu khó thấy: nó lọc bộ test bằng chính đại lượng mà bộ test sinh ra để hiệu
chỉnh. Câu ngoài phạm vi nào vô tình bị chấm điểm cao sẽ bị vứt đi, nên phần dữ
liệu còn lại chỉ gồm những ca hệ thống vốn đã làm tốt — τ chọn ra từ đó sẽ đẹp
hơn sự thật, và không có gì trong kết quả để lộ điều đó.

Ở đây kiểm bằng **nội dung**: lấy các đoạn được truy xuất ra, hỏi một mô hình
*"các đoạn này có trả lời được câu hỏi không?"*. Câu nào trả lời được thì thật
ra nằm trong phạm vi và bị loại. Phép kiểm này độc lập với thang điểm τ, nên
không làm hỏng phép hiệu chỉnh sau đó. Điểm rerank vẫn được ghi lại — như **dữ
liệu quan sát được**, không phải như bộ lọc.

Mặt trái: câu hỏi dễ hơn câu hỏi thật
--------------------------------------
Đặt câu hỏi từ một đoạn làm ground truth đáng tin, nhưng cũng làm câu hỏi thừa
hưởng **từ vựng** của chính đoạn đó — và truy xuất tìm lại nó gần như chắc chắn.
Lượt chấm đầu tiên cho điểm cross-encoder 0.98–0.99 trên phần lớn câu trong
phạm vi, tức là bài toán dễ hơn hẳn thực tế.

Prompt vì vậy yêu cầu diễn đạt lại bằng từ ngữ đời thường. Nó thu hẹp khoảng
cách chứ không xoá được: người rà vẫn phải viết lại những câu chép quá sát, và
`eval/README.md` ghi rõ Context Recall đo ở đây là **chặn trên**, không phải kỳ
vọng.

Con người vẫn phải rà
---------------------
AC-6 yêu cầu **người rà soát và sửa 100%**, và ghi lại tỉ lệ loại/sửa như một
phần của phương pháp. Script này dừng ở trạng thái `pending`; `eval/review.py`
là chỗ ghi nhận việc rà.

    python eval/build_dataset.py --nap          # nạp tài liệu vào notebook đánh giá
    python eval/build_dataset.py --so-cau 100   # sinh bộ câu hỏi
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters.embedding import get_embedding_provider
from app.adapters.extract import ExtractionError
from app.adapters.llm import get_llm_provider
from app.models.base import session_scope
from app.models.knowledge import Notebook, Source, SourceChunk, User
from app.ports.llm import LLMProvider
from app.services.ingest import SUFFIX_TO_KIND, ingest_file
from app.services.retrieval import retrieve
from sqlalchemy import select

DOCS = ROOT / "eval" / "dataset" / "documents"
OUT = ROOT / "eval" / "dataset" / "questions.json"

OWNER = "eval@documind.local"
NOTEBOOK = "Bộ đánh giá"

# Hạt giống cố định — US-045 AC-5 yêu cầu chạy lại ra cùng kết quả.
SEED = 20260821

# Đoạn quá ngắn không đủ nội dung để đặt một câu hỏi có đáp án rõ ràng.
MIN_CHUNK_CHARS = 300

# Số đoạn đưa cho bộ kiểm đọc khi xác minh một câu là ngoài phạm vi.
OUT_OF_SCOPE_CHECK_CHUNKS = 5

# Bản miễn phí của Gemini cho 20 request mỗi phút. Adapter có thử lại khi bị
# chặn, nhưng chờ rồi thử lại là cách xử lý *sự cố*, không phải cách chạy bình
# thường: 100 câu hỏi gọi liên tiếp sẽ dính 429 gần như mọi lượt và biến một
# việc mười phút thành một giờ. Giữ nhịp ngay từ đầu rẻ hơn nhiều.
GOI_MOI_PHUT = 18  # chừa biên dưới hạn mức


class Nhip:
    """Giãn các lượt gọi ra cho đủ thưa."""

    def __init__(self, moi_phut: int) -> None:
        self.khoang = 60.0 / moi_phut
        self._lan_truoc = 0.0

    async def cho(self) -> None:
        con = self.khoang - (time.monotonic() - self._lan_truoc)
        if con > 0:
            await asyncio.sleep(con)
        self._lan_truoc = time.monotonic()

KIEM_NGOAI_PHAM_VI = """Bạn nhận một câu hỏi và vài đoạn trích từ tài liệu.

Trả lời đúng MỘT từ:

CO    — các đoạn này trả lời được câu hỏi, dù chỉ một phần
KHONG — các đoạn này không chứa thông tin để trả lời

Chỉ xét thông tin nằm trong các đoạn. Đừng dùng kiến thức bên ngoài."""

LOAI_CAU_HOI = {
    "fact_single": "hỏi sự kiện đơn — đáp án nằm gọn trong một câu",
    "inference": "cần suy luận hoặc diễn giải, không chép lại nguyên văn được",
    "numeric": "hỏi về con số, thời hạn, tỉ lệ hoặc mốc thời gian",
}

SINH_CAU_HOI = """Bạn nhận một đoạn trích từ văn bản pháp quy tiếng Việt.

Hãy đặt MỘT câu hỏi mà đoạn này trả lời được đầy đủ, và viết đáp án.

QUY TẮC
1. Câu hỏi phải trả lời được CHỈ bằng đoạn đã cho. Không hỏi điều phải suy ra \
từ nơi khác.
2. Câu hỏi phải tự đứng được: người đọc không nhìn thấy đoạn này vẫn hiểu đang \
hỏi gì. KHÔNG dùng "đoạn này", "theo trên", "điều khoản nêu trên".
3. **Hỏi bằng lời của người dùng, không bằng lời của văn bản.** Diễn đạt lại \
bằng từ ngữ đời thường. TRÁNH chép lại các cụm từ đặc trưng của đoạn — nếu đoạn \
viết "điểm trung bình tích lũy" thì hỏi "điểm trung bình toàn khoá"; nếu đoạn \
viết "nghỉ học tạm thời" thì hỏi "bảo lưu kết quả". Người thật hỏi bằng từ ngữ \
của họ, không phải từ ngữ trong quy chế.
4. Đáp án viết ngắn gọn 1–3 câu, chỉ dùng thông tin trong đoạn.
5. Loại câu hỏi phải là MỘT trong: {loai}

Trả về ĐÚNG khuôn dạng sau, không thêm gì khác:

CÂU HỎI: <câu hỏi>
ĐÁP ÁN: <đáp án>
LOẠI: <một trong các loại trên>"""

SINH_NGOAI_PHAM_VI = """Bạn nhận danh sách chủ đề của một bộ tài liệu về quy \
chế đào tạo đại học Việt Nam.

Hãy đặt {n} câu hỏi **hợp lý về mặt chủ đề** nhưng **chắc chắn không có đáp án** \
trong loại tài liệu đó.

QUY TẮC
1. Câu hỏi phải nghe như một người dùng thật sẽ hỏi hệ thống này — cùng lĩnh \
vực giáo dục đại học, không phải hỏi về thời tiết hay bóng đá.
2. Nhưng đáp án phải nằm NGOÀI phạm vi một bản quy chế đào tạo: ví dụ số liệu \
thống kê cả nước, tin tức, giá cả thị trường, thông tin về một trường cụ thể \
không có trong tài liệu.
3. Mỗi dòng một câu hỏi, đánh số từ 1. Không thêm lời dẫn.

CÁC CHỦ ĐỀ CÓ TRONG TÀI LIỆU:
{chu_de}"""

_CAU_HOI = re.compile(r"CÂU HỎI:\s*(.+)")
_DAP_AN = re.compile(r"ĐÁP ÁN:\s*(.+?)(?=\nLOẠI:|\Z)", re.DOTALL)
_LOAI = re.compile(r"LOẠI:\s*(\w+)")


@dataclass
class CauHoi:
    id: str
    question: str
    answer: str
    type: str
    source: str
    """Đường dẫn tương đối của tệp nguồn — nhãn neo vào đây, không vào chunk_id."""

    page: int | None
    char_start: int
    char_end: int
    context: str
    review: dict = field(default_factory=lambda: {"status": "pending", "edited": False})


@dataclass
class NgoaiPhamVi:
    id: str
    question: str
    type: str = "out_of_scope"
    top_score: float = 0.0
    """Điểm truy xuất cao nhất đo được — bằng chứng câu này thật sự ngoài phạm vi."""

    review: dict = field(default_factory=lambda: {"status": "pending", "edited": False})


# ══════════════════════════════════════════════════════
# Nạp tài liệu
# ══════════════════════════════════════════════════════


async def nap_tai_lieu() -> None:
    files = sorted(
        p for p in DOCS.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIX_TO_KIND
    )
    if not files:
        print(f"Không có tài liệu nào trong {DOCS}", file=sys.stderr)
        return

    embedder = get_embedding_provider()
    print(f"Nhúng: {embedder.name}")

    ok = 0
    for i, path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {path.name}")
        try:
            with session_scope() as s:
                r = await ingest_file(
                    s, path, notebook_title=NOTEBOOK,
                    embedder=embedder, owner_email=OWNER,
                )
            print(f"        {r.chunk_count} đoạn · {r.page_count} trang · "
                  f"offset {'✓' if r.invariant_holds else '✗ SAI'}")
            ok += 1
        except ExtractionError as e:
            print(f"        BỎ QUA {e.code}")

    print(f"\nNạp được {ok}/{len(files)} tệp.")


# ══════════════════════════════════════════════════════
# Sinh câu hỏi trong phạm vi
# ══════════════════════════════════════════════════════


async def _hoi_mot_doan(
    llm: LLMProvider, noi_dung: str, nhip: Nhip
) -> tuple[str, str, str] | None:
    prompt = SINH_CAU_HOI.format(loai=", ".join(LOAI_CAU_HOI))
    await nhip.cho()
    try:
        pieces = [
            p
            async for p in llm.stream(
                prompt, [{"role": "user", "content": noi_dung[:4000]}],
                temperature=0.3, max_tokens=400,
            )
        ]
    except Exception as exc:
        print(f"    lỗi mô hình: {type(exc).__name__}: {str(exc)[:80]}")
        return None

    raw = "".join(pieces)
    q, a, t = _CAU_HOI.search(raw), _DAP_AN.search(raw), _LOAI.search(raw)
    if not (q and a):
        return None
    loai = (t.group(1).strip() if t else "fact_single")
    if loai not in LOAI_CAU_HOI:
        loai = "fact_single"
    return q.group(1).strip(), " ".join(a.group(1).split()), loai


async def sinh_trong_pham_vi(
    so_cau: int, out: list[CauHoi], luu: Callable[[], None]
) -> None:
    llm = get_llm_provider()
    print(f"Sinh câu hỏi bằng: {llm.name}")

    with session_scope() as s:
        user = s.scalar(select(User).where(User.email == OWNER))
        if user is None:
            print("Chưa nạp tài liệu. Chạy: python eval/build_dataset.py --nap",
                  file=sys.stderr)
            return
        nb = s.scalar(select(Notebook).where(Notebook.user_id == user.id))
        rows = s.execute(
            select(
                SourceChunk.content, SourceChunk.page_no,
                SourceChunk.char_start, SourceChunk.char_end,
                Source.storage_key,
            )
            .join(Source, Source.id == SourceChunk.source_id)
            .where(SourceChunk.notebook_id == nb.id)
        ).all()

    doan = [r for r in rows if len(r.content) >= MIN_CHUNK_CHARS]
    print(f"Có {len(doan)} đoạn đủ dài trên tổng {len(rows)}.")

    # Chọn ngẫu nhiên nhưng TẤT ĐỊNH, và rải đều trên các tệp để không dồn hết
    # câu hỏi vào một tài liệu.
    rng = random.Random(SEED)
    theo_tep: dict[str, list] = {}
    for r in doan:
        theo_tep.setdefault(r.storage_key, []).append(r)
    for v in theo_tep.values():
        rng.shuffle(v)

    chon: list = []
    ten_tep = sorted(theo_tep)
    while len(chon) < so_cau and any(theo_tep[t] for t in ten_tep):
        for t in ten_tep:
            if theo_tep[t] and len(chon) < so_cau:
                chon.append(theo_tep[t].pop())

    nhip = Nhip(GOI_MOI_PHUT)
    print(f"Nhịp gọi: {GOI_MOI_PHUT}/phút — dự kiến "
          f"{len(chon) * 60 / GOI_MOI_PHUT / 60:.0f} phút cho phần này.")

    for i, r in enumerate(chon, 1):
        ket_qua = await _hoi_mot_doan(llm, r.content, nhip)
        if ket_qua is None:
            print(f"  [{i}/{len(chon)}] bỏ qua — mô hình không trả đúng khuôn dạng")
            continue
        q, a, loai = ket_qua
        out.append(
            CauHoi(
                id=f"q{len(out) + 1:03d}",
                question=q, answer=a, type=loai,
                source=Path(r.storage_key).name,
                page=r.page_no,
                char_start=r.char_start, char_end=r.char_end,
                context=r.content,
            )
        )
        print(f"  [{i}/{len(chon)}] {loai:<12} {q[:64]}", flush=True)
        luu()


# ══════════════════════════════════════════════════════
# Sinh câu hỏi ngoài phạm vi và kiểm chứng
# ══════════════════════════════════════════════════════


async def sinh_ngoai_pham_vi(
    so_cau: int, giu: list[NgoaiPhamVi], luu: Callable[[], None]
) -> None:
    llm = get_llm_provider()
    embedder = get_embedding_provider()

    with session_scope() as s:
        user = s.scalar(select(User).where(User.email == OWNER))
        nb = s.scalar(select(Notebook).where(Notebook.user_id == user.id))
        tieu_de = s.scalars(
            select(SourceChunk.heading_path)
            .where(SourceChunk.notebook_id == nb.id, SourceChunk.heading_path.isnot(None))
            .distinct()
            .limit(40)
        ).all()

    # Sinh dư rồi lọc — bước kiểm chứng bên dưới sẽ loại bớt.
    prompt = SINH_NGOAI_PHAM_VI.format(
        n=int(so_cau * 1.6), chu_de="\n".join(f"- {t}" for t in tieu_de[:40])
    )
    pieces = [
        p
        async for p in llm.stream(
            prompt, [{"role": "user", "content": "Hãy đặt câu hỏi."}],
            temperature=0.7, max_tokens=1500,
        )
    ]
    ung_vien = [
        re.sub(r"^\s*\d+[.)]\s*", "", line).strip()
        for line in "".join(pieces).splitlines()
        if re.match(r"^\s*\d+[.)]", line)
    ]
    print(f"Mô hình đề xuất {len(ung_vien)} câu ngoài phạm vi. Đang kiểm chứng …")

    from app.adapters.rerank import get_rerank_provider
    from app.services.grounding import decide

    reranker = get_rerank_provider()
    nhip = Nhip(GOI_MOI_PHUT)
    loai_bo = 0

    for q in ung_vien:
        if len(giu) >= so_cau:
            break

        # Mở phiên RIÊNG cho từng câu, đóng ngay sau khi truy xuất xong.
        #
        # Vòng lặp này dành phần lớn thời gian để chờ mô hình và chờ
        # cross-encoder trên CPU — hàng chục phút cho một lượt đầy đủ. Giữ một
        # kết nối mở suốt chừng ấy là để nó phơi ra trước mọi thứ có thể cắt
        # đứt: hết hạn nhàn rỗi, mạng chập chờn, hay Docker tắt giữa chừng.
        # Lấy kết nối từ pool cho từng câu gần như không tốn gì, và mỗi lần lấy
        # đều được `pool_pre_ping` kiểm tra lại.
        with session_scope() as s:
            user = s.scalar(select(User).where(User.email == OWNER))
            nb = s.scalar(select(Notebook).where(Notebook.user_id == user.id))
            r = retrieve(s, q, notebook_id=nb.id, embedder=embedder, owner_id=user.id)
            d = decide(q, r, reranker=reranker)

        # Quyết định GIỮ hay LOẠI dựa vào việc các đoạn có trả lời được câu hỏi
        # không — không dựa vào `d.top_score`. Điểm chỉ được ghi lại.
        if await _co_dap_an_khong(llm, q, d.chunks, nhip):
            loai_bo += 1
            print(f"  loại (điểm {d.top_score:.2f}, tài liệu CÓ trả lời): {q[:56]}",
                  flush=True)
            continue

        giu.append(NgoaiPhamVi(id=f"o{len(giu) + 1:03d}", question=q,
                               top_score=round(d.top_score, 4)))
        print(f"  giữ  (điểm {d.top_score:.2f}): {q[:66]}", flush=True)
        luu()

    luu()
    print(f"\nGiữ {len(giu)}, loại {loai_bo} vì tài liệu thật ra có trả lời được.")
    if giu:
        diem = [c.top_score for c in giu]
        print(f"Điểm truy xuất của nhóm ngoài phạm vi: thấp nhất {min(diem):.3f}, "
              f"cao nhất {max(diem):.3f}, trung bình {sum(diem) / len(diem):.3f}")
        print("Đây là dữ liệu quan sát, KHÔNG phải bộ lọc — τ được chọn từ chính "
              "phân bố này ở US-047.")


async def _co_dap_an_khong(
    llm: LLMProvider, cau_hoi: str, chunks, nhip: Nhip
) -> bool:
    """Các đoạn được truy xuất có trả lời được câu hỏi không.

    Khi bộ kiểm hỏng thì trả về ``True`` — tức là **loại** câu hỏi đó. Nghiêng
    về loại là lựa chọn có chủ ý: một câu ngoài phạm vi giả mạo lọt vào sẽ làm
    lệch phép hiệu chỉnh τ và không có gì phát hiện ra; mất một câu chỉ làm bộ
    test nhỏ đi một chút.
    """
    if not chunks:
        return False

    ngu_canh = "\n\n".join(
        f"[{i}] {c.candidate.content[:1200]}"
        for i, c in enumerate(chunks[:OUT_OF_SCOPE_CHECK_CHUNKS], 1)
    )
    await nhip.cho()
    try:
        pieces = [
            p
            async for p in llm.stream(
                KIEM_NGOAI_PHAM_VI,
                [{"role": "user",
                  "content": f"CÁC ĐOẠN:\n{ngu_canh}\n\nCÂU HỎI: {cau_hoi}"}],
                temperature=0.0, max_tokens=8,
            )
        ]
    except Exception as exc:
        print(f"    bộ kiểm lỗi ({type(exc).__name__}), loại câu này cho chắc")
        return True

    return "KHONG" not in "".join(pieces).strip().upper()


# ══════════════════════════════════════════════════════


def _ghi(trong: list[CauHoi], ngoai: list[NgoaiPhamVi]) -> None:
    """Ghi bộ dữ liệu ra đĩa.

    Gọi **sau mỗi câu**, không phải một lần ở cuối. Phần trong phạm vi tốn một
    lượt gọi mô hình cho mỗi câu; để một lỗi ở bước sau xoá sạch công đó là điều
    đã xảy ra thật, và nó tốn nửa giờ hạn mức API để học.
    """
    llm = get_llm_provider()
    embedder = get_embedding_provider()
    OUT.write_text(
        json.dumps(
            {
                "metadata": {
                    "created": datetime.now(UTC).isoformat(timespec="seconds"),
                    "seed": SEED,
                    "generator_model": llm.name,
                    "embedding_model": embedder.name,
                    "note": (
                        "Câu hỏi do mô hình sinh TỪ một đoạn cụ thể, nên ground "
                        "truth đúng theo cấu tạo. Trạng thái 'pending' nghĩa là "
                        "CHƯA có người rà — US-044 AC-6 yêu cầu rà 100% trước khi "
                        "dùng số liệu."
                    ),
                    "question_types": LOAI_CAU_HOI,
                },
                "in_scope": [asdict(c) for c in trong],
                "out_of_scope": [asdict(c) for c in ngoai],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


async def main_async(args: argparse.Namespace) -> int:
    if args.nap:
        await nap_tai_lieu()
        return 0

    trong: list[CauHoi] = []
    ngoai: list[NgoaiPhamVi] = []

    await sinh_trong_pham_vi(args.so_cau, trong, lambda: _ghi(trong, ngoai))
    if not trong:
        return 1

    await sinh_ngoai_pham_vi(args.ngoai_pham_vi, ngoai, lambda: _ghi(trong, ngoai))
    _ghi(trong, ngoai)

    print(f"\nĐã ghi {len(trong)} câu trong phạm vi + {len(ngoai)} câu ngoài "
          f"phạm vi vào {OUT.relative_to(ROOT)}")
    print("\nBƯỚC BẮT BUỘC TIẾP THEO: rà soát bằng  python eval/review.py")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Dựng bộ câu hỏi có nhãn (US-044).")
    ap.add_argument("--nap", action="store_true",
                    help="Nạp tài liệu vào notebook đánh giá rồi dừng")
    ap.add_argument("--so-cau", type=int, default=100,
                    help="Số câu hỏi trong phạm vi (US-044 AC-2)")
    ap.add_argument("--ngoai-pham-vi", type=int, default=30,
                    help="Số câu hỏi ngoài phạm vi (US-044 AC-4)")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
