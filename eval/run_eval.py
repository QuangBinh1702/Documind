"""Đo chất lượng hệ thống trên bộ câu hỏi có nhãn — US-045.

Hai loại chỉ số, và lý do phải tách chúng ra
---------------------------------------------
**Đo được bằng phép so khớp** — Context Recall, Context Precision, Citation
Accuracy. Chúng chỉ cần so khoảng ký tự của đoạn được truy xuất với khoảng ký tự
của nhãn. Không mô hình nào tham gia, nên chạy lại luôn ra đúng cùng con số, và
không ai cãi được kết quả.

Cẩn thận với **định nghĩa** của nhóm này: chúng dễ đo nhưng cũng dễ định nghĩa
sai theo cách không ai nhận ra. Context Precision từng được tính là *"tỉ lệ đoạn
trong ngữ cảnh mà trùng nhãn"*; nhãn chỉ có một đoạn còn ngữ cảnh có tám, nên
chỉ số đó bị chặn trên ở 0.125 — thấp hơn cả ngưỡng nghiệm thu 0.70, và **không
mẫu nào đạt được dù truy xuất hoàn hảo**. Bảng kết quả trông vẫn bình thường,
chỉ là mọi dòng đều trượt. Xem chú thích ở `KetQua.context_precision`.

**Phải nhờ mô hình chấm** — Faithfulness, Answer Relevancy. Không có cách nào
so khớp chuỗi để biết một câu trả lời có bịa hay không. Đây là chỗ phương pháp
yếu nhất của toàn bộ Chương 5, nên nó phải được nói thẳng chứ không trộn lẫn vào
nhóm trên.

US-045 AC-9 yêu cầu **mô hình chấm khác mô hình sinh**. Một mô hình chấm chính
câu nó vừa viết thì thiên vị theo hướng dễ đoán. Ở đây bộ sinh là
`GEMINI_MODEL`, bộ chấm là `EVAL_JUDGE_MODEL`; nếu hai giá trị trùng nhau,
script vẫn chạy nhưng ghi thẳng vào tệp kết quả rằng đây là một hạn chế về
phương pháp.

Vì sao so khoảng ký tự chứ không so `chunk_id`
------------------------------------------------
Nhãn neo vào `(tệp, char_start, char_end)` trên văn bản gốc. Một đoạn được tính
là **trúng** khi khoảng của nó chồng lấn khoảng của nhãn. Nhờ vậy đổi
`CHUNK_TOKENS` hay nạp lại tài liệu không làm hỏng bộ test — trong khi neo vào
`chunk_id` thì chỉ cần nạp lại một lần là mọi nhãn vô nghĩa.

Chạy lại được và chạy tiếp được
--------------------------------
Mỗi câu hỏi ghi kết quả ngay khi xong. Một lượt chạy đầy đủ trên CPU mất hàng
giờ; mất điện giữa chừng không được phép xoá sạch. Chạy lại cùng lệnh sẽ bỏ qua
những câu đã có kết quả.

    python eval/run_eval.py                    # đầy đủ
    python eval/run_eval.py --chi-truy-xuat    # bỏ phần sinh, chỉ đo truy xuất
    python eval/run_eval.py --nhan cau-hinh-D  # đặt tên cho lượt chạy
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.adapters.embedding import get_embedding_provider
from app.adapters.llm import get_llm_provider
from app.adapters.llm.gemini import GeminiLLMProvider
from app.adapters.rerank import get_rerank_provider
from app.models.base import session_scope
from app.models.knowledge import Notebook, User
from app.ports.llm import LLMProvider
from app.services.answer import answer_question, final_result
from app.settings import settings
from sqlalchemy import select

QUESTIONS = ROOT / "eval" / "dataset" / "questions.json"
RESULTS = ROOT / "eval" / "results"

OWNER = "eval@documind.local"

# Ngưỡng tối thiểu để một mẫu được tính là ĐẠT — SPEC.md US-045 AC-2.
NGUONG = {
    "faithfulness": 0.80,
    "answer_relevancy": 0.80,
    "context_recall": 0.75,
    "context_precision": 0.70,
    "citation_accuracy": 0.85,
}

# Nhịp gọi — bản miễn phí cho 20 request mỗi phút cho mỗi mô hình.
GOI_MOI_PHUT = 18


class Nhip:
    def __init__(self, moi_phut: int) -> None:
        self.khoang = 60.0 / moi_phut
        self._lan_truoc = 0.0

    async def cho(self) -> None:
        con = self.khoang - (time.monotonic() - self._lan_truoc)
        if con > 0:
            await asyncio.sleep(con)
        self._lan_truoc = time.monotonic()


# ══════════════════════════════════════════════════════
# Bộ chấm bằng mô hình
# ══════════════════════════════════════════════════════

CHAM_FAITHFULNESS = """Bạn kiểm tra một câu trả lời có bám vào tài liệu không.

Tách câu trả lời thành từng khẳng định. Với mỗi khẳng định, xét xem nó có được
các đoạn tài liệu chứng thực hay không. "Được chứng thực" nghĩa là nội dung nằm
rõ ràng trong đoạn — không phải nghe hợp lý là được.

Trả về ĐÚNG hai dòng:
TỔNG: <số khẳng định>
ĐƯỢC CHỨNG THỰC: <số khẳng định được chứng thực>"""

CHAM_RELEVANCY = """Bạn chấm mức độ câu trả lời TRẢ LỜI ĐÚNG câu hỏi được hỏi.

Chỉ xét sự phù hợp với câu hỏi. KHÔNG xét đúng sai về mặt sự thật — việc đó do
chỉ số khác lo.

Thang điểm:
1.0  trả lời trực tiếp và đầy đủ
0.7  trả lời được nhưng thiếu một phần, hoặc vòng vo
0.4  chỉ chạm tới chủ đề, không trả lời câu hỏi
0.0  lạc đề, hoặc từ chối trả lời

Trả về ĐÚNG một dòng:
ĐIỂM: <một trong 1.0, 0.7, 0.4, 0.0>"""

CHAM_TRICH_DAN = """Bạn kiểm tra các TRÍCH DẪN trong một câu trả lời có trỏ \
đúng chỗ không.

Câu trả lời gắn số đoạn dạng [1], [2] vào từng khẳng định. Với MỖI lần gắn số,
xét xem khẳng định đi kèm có thật sự nằm trong ĐÚNG đoạn mang số đó hay không.

Đúng   — nội dung của khẳng định có trong đoạn được gắn số.
Sai    — khẳng định không có trong đoạn ấy, dù có thể nằm ở đoạn khác.

Chỉ xét trích dẫn có trỏ đúng đoạn hay không. KHÔNG xét câu trả lời hay hay dở,
cũng KHÔNG trừ điểm vì trích dẫn nhiều nguồn: một câu trả lời nêu quy định của
ba tài liệu khác nhau và gắn đúng số cho từng cái là HOÀN TOÀN ĐÚNG.

Trả về ĐÚNG hai dòng:
TỔNG: <số lần gắn số>
ĐÚNG: <số lần gắn đúng đoạn>"""

_TONG = re.compile(r"TỔNG:\s*(\d+)")
_CHUNG_THUC = re.compile(r"ĐƯỢC CHỨNG THỰC:\s*(\d+)")
_DUNG = re.compile(r"ĐÚNG:\s*(\d+)")
_DIEM = re.compile(r"ĐIỂM:\s*([\d.]+)")


async def _goi(llm: LLMProvider, system: str, user: str, nhip: Nhip) -> str:
    await nhip.cho()
    try:
        return "".join([
            p
            async for p in llm.stream(
                system, [{"role": "user", "content": user}],
                temperature=0.0, max_tokens=300,
            )
        ])
    except Exception as exc:
        print(f"      bộ chấm lỗi: {type(exc).__name__}: {str(exc)[:70]}")
        return ""


async def cham_faithfulness(
    llm: LLMProvider, answer: str, contexts: list[str], nhip: Nhip
) -> float | None:
    """Tỉ lệ khẳng định được ngữ cảnh chứng thực.

    Trả về ``None`` khi không chấm được — **không** trả về 0. Một lượt gọi hỏng
    không phải là một câu trả lời bịa; gộp hai thứ đó lại là bóp méo số liệu
    theo hướng xấu đi mà không có gì trong kết quả nói ra điều đó.
    """
    if not answer.strip() or not contexts:
        return None
    ngu_canh = "\n\n".join(f"[{i}] {c[:1500]}" for i, c in enumerate(contexts, 1))
    raw = await _goi(
        llm, CHAM_FAITHFULNESS,
        f"CÁC ĐOẠN:\n{ngu_canh}\n\nCÂU TRẢ LỜI:\n{answer}", nhip,
    )
    tong, chung = _TONG.search(raw), _CHUNG_THUC.search(raw)
    if not (tong and chung):
        return None
    n = int(tong.group(1))
    return round(int(chung.group(1)) / n, 4) if n else None


async def cham_trich_dan(
    llm: LLMProvider, answer: str, contexts: list[str], nhip: Nhip
) -> float | None:
    """Tỉ lệ lần gắn số trỏ đúng đoạn — US-045.

    Đây là chỉ số đo đúng thứ đồ án hứa: *"mỗi khẳng định gắn số đoạn, bấm vào
    số đó là ra đúng chỗ nội dung được lấy"*. Nó khác hẳn `citation_precision_gold`
    bên dưới — xem chú thích ở đó.
    """
    if not answer.strip() or not contexts:
        return None
    if "[" not in answer:
        return None

    ngu_canh = "\n\n".join(f"[{i}] {c[:1500]}" for i, c in enumerate(contexts, 1))
    raw = await _goi(
        llm, CHAM_TRICH_DAN,
        f"CÁC ĐOẠN:\n{ngu_canh}\n\nCÂU TRẢ LỜI:\n{answer}", nhip,
    )
    tong, dung = _TONG.search(raw), _DUNG.search(raw)
    if not (tong and dung):
        return None
    n = int(tong.group(1))
    return round(int(dung.group(1)) / n, 4) if n else None


async def cham_relevancy(
    llm: LLMProvider, question: str, answer: str, nhip: Nhip
) -> float | None:
    if not answer.strip():
        return None
    raw = await _goi(
        llm, CHAM_RELEVANCY, f"CÂU HỎI: {question}\n\nCÂU TRẢ LỜI: {answer}", nhip
    )
    m = _DIEM.search(raw)
    return float(m.group(1)) if m else None


# ══════════════════════════════════════════════════════
# Chỉ số đo bằng so khớp
# ══════════════════════════════════════════════════════


def _trung(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """Hai khoảng ký tự có chồng lấn không."""
    return a_start < b_end and a_end > b_start


@dataclass
class KetQua:
    id: str
    question: str
    type: str
    answer_kind: str = ""
    answer: str = ""

    context_recall: float = 0.0
    """Nhãn có nằm trong các đoạn được truy xuất không — 1.0 hoặc 0.0."""

    context_precision: float = 0.0
    """Nghịch đảo thứ hạng của đoạn chứa nhãn: hạng 1 cho 1.0, hạng 4 cho 0.25.

    **Không phải** tỉ lệ "bao nhiêu đoạn trong ngữ cảnh là đoạn đúng". Nhãn ở
    đây chỉ có MỘT đoạn, còn ngữ cảnh có `RERANK_TOP_K` đoạn, nên định nghĩa
    theo tỉ lệ bị chặn trên ở `1/top_k` = 0.125 — thấp hơn cả ngưỡng nghiệm thu
    0.70, tức là không mẫu nào đạt được dù truy xuất hoàn hảo. Đã gặp thật ở
    lượt chạy đầu: mọi mẫu đều ra đúng 0.12.

    Nghịch đảo thứ hạng đo đúng thứ cần đo — *"đoạn đúng có được xếp lên đầu
    không?"* — và trùng với định nghĩa Context Precision của RAGAS trong trường
    hợp một đoạn liên quan duy nhất.
    """

    context_rank: int | None = None
    """Thứ hạng của đoạn chứa nhãn, 1 là cao nhất. `None` nếu không truy xuất
    được — giữ riêng để phân tích, vì nghịch đảo che mất khoảng cách giữa hạng
    5 và hạng 8."""

    citation_accuracy: float | None = None
    """Tỉ lệ lần gắn số trỏ ĐÚNG đoạn, do mô hình chấm.

    Đây là chỉ số **cổng**: nó đo đúng lời hứa của hệ thống — bấm vào một số
    trích dẫn là ra đúng chỗ nội dung được lấy. `None` khi câu trả lời không có
    trích dẫn nào, khác hẳn với "có trích dẫn nhưng trỏ sai".
    """

    citation_recall_gold: float | None = None
    """Câu trả lời có trích dẫn đoạn chứa nhãn không — 1.0 hoặc 0.0.

    Đo được bằng so khớp khoảng ký tự, không cần mô hình, nên tái lập tuyệt đối.
    """

    citation_precision_gold: float | None = None
    """Tỉ lệ trích dẫn trùng đoạn chứa nhãn. **KHÔNG dùng làm cổng** — ghi lại
    để phân tích, và vì bản trước từng dùng nó làm cổng.

    Vì sao nó không đo được chất lượng trích dẫn: bộ ngữ liệu gồm quy chế của
    NHIỀU trường cùng bàn một chủ đề, nhưng mỗi câu hỏi chỉ gắn MỘT đoạn vàng.
    Một câu trả lời tốt nêu được sự khác nhau giữa bốn quy chế và gắn đúng số
    cho từng cái sẽ nhận điểm 1/4 — bị phạt vì đã làm đúng.

    Đo thật ở lượt chạy 10 câu: bốn câu "trượt" nhận đúng 0.20, 0.25, 0.25 và
    0.33 — tức là 1/5, 1/4, 1/4, 1/3, khớp chính xác số marker mà câu trả lời
    đã dùng. Đó là dấu vân tay của một công thức bị chặn trên bởi `1/N`, không
    phải của một hệ thống trích dẫn sai.
    """

    faithfulness: float | None = None
    answer_relevancy: float | None = None

    top_score: float = 0.0
    latency_ms: int = 0
    nhom_loi: str = ""
    """Một trong bốn nhóm ở US-045 AC-7, rỗng nếu mẫu này đạt."""

    contexts: list[str] = field(default_factory=list)

    @property
    def dat(self) -> bool:
        """Đạt khi MỌI chỉ số đo được đều vượt ngưỡng tối thiểu.

        Chỉ số `None` không được tính là đạt: không đo được thì không kết luận
        được, và tính nó là đạt sẽ thổi phồng pass rate.
        """
        for ten, nguong in NGUONG.items():
            gia_tri = getattr(self, ten)
            if gia_tri is None or gia_tri < nguong:
                return False
        return True


def phan_loai_loi(kq: KetQua) -> str:
    """Xếp một mẫu trượt vào một trong bốn nhóm — US-045 AC-7.

    Thứ tự xét quan trọng: truy xuất trượt thì mọi thứ sau đó đều trượt theo,
    nên phải quy về nguyên nhân gốc chứ không quy về triệu chứng cuối cùng.
    """
    if kq.dat:
        return ""
    if kq.context_recall < NGUONG["context_recall"]:
        return "retrieval_failure"
    # `context_precision` cũng là lỗi truy xuất: đoạn chứa đáp án có được lấy về
    # nhưng bị xếp hạng thấp. Thiếu nhánh này thì những mẫu ấy rơi vào "khac" —
    # và "khac" là chỗ nguyên nhân đi ẩn mình. Đo thật trên 10 câu: hai mẫu vào
    # "khac", cả hai đều là `prec=0.50`, tức là hạng 2 chứ không phải hạng 1.
    if kq.context_precision < NGUONG["context_precision"]:
        return "retrieval_ranking"
    if kq.faithfulness is not None and kq.faithfulness < NGUONG["faithfulness"]:
        return "generation_grounding"
    if kq.answer_relevancy is not None and kq.answer_relevancy < NGUONG["answer_relevancy"]:
        return "generation_answer"
    if kq.citation_accuracy is None or kq.citation_accuracy < NGUONG["citation_accuracy"]:
        return "citation_error"
    return "khac"


# ══════════════════════════════════════════════════════


async def chay_mot_cau(
    session, cau: dict, nb_id, user_id, providers, judge, nhip_judge, chi_truy_xuat: bool
) -> KetQua:
    emb, rr, llm = providers
    kq = KetQua(id=cau["id"], question=cau["question"], type=cau["type"])

    events = [
        e
        async for e in answer_question(
            session, cau["question"], notebook_id=nb_id,
            embedder=emb, reranker=rr, llm=llm, owner_id=user_id,
        )
    ]
    r = final_result(events)
    kq.answer_kind = r.kind
    kq.answer = r.answer
    kq.latency_ms = r.latency_ms
    kq.top_score = round(r.decision.top_score, 4) if r.decision else 0.0

    chunks = r.decision.chunks if r.decision else []
    kq.contexts = [c.candidate.content for c in chunks]

    # ── Chỉ số so khớp ─────────────────────────────────
    # Các đoạn đã xếp theo điểm, cao nhất trước, nên vị trí trong danh sách
    # chính là thứ hạng.
    hang = next(
        (
            i
            for i, c in enumerate(chunks, 1)
            if _trung(c.candidate.char_start, c.candidate.char_end,
                      cau["char_start"], cau["char_end"])
        ),
        None,
    )
    kq.context_rank = hang
    kq.context_recall = 1.0 if hang else 0.0
    kq.context_precision = round(1.0 / hang, 4) if hang else 0.0

    if r.citations:
        trung_nhan = sum(
            1 for c in r.citations
            if _trung(c.char_start, c.char_end, cau["char_start"], cau["char_end"])
        )
        kq.citation_recall_gold = 1.0 if trung_nhan else 0.0
        kq.citation_precision_gold = round(trung_nhan / len(r.citations), 4)

    # ── Chỉ số cần mô hình chấm ────────────────────────
    if not chi_truy_xuat and r.kind == "grounded":
        kq.faithfulness = await cham_faithfulness(judge, r.answer, kq.contexts, nhip_judge)
        kq.answer_relevancy = await cham_relevancy(judge, cau["question"], r.answer, nhip_judge)
        kq.citation_accuracy = await cham_trich_dan(judge, r.answer, kq.contexts, nhip_judge)

    kq.nhom_loi = phan_loai_loi(kq)
    return kq


def _ten_bo_sinh() -> str:
    """Tên mô hình ĐANG sinh câu trả lời.

    Hỏi adapter thay vì đọc `settings.gemini_model`. Từ khi Fast Mode chọn được
    nhà cung cấp, hai thứ đó khác nhau: chạy Ollama Cloud mà siêu dữ liệu vẫn
    ghi tên mô hình Gemini thì mục "tái lập được" của US-045 AC-5 ghi sai chính
    thứ nó sinh ra để ghi đúng.
    """
    return get_llm_provider().name


def _sieu_du_lieu(judge_model: str, nhan: str, chi_truy_xuat: bool) -> dict:
    """Mọi thứ cần để dựng lại đúng lượt chạy này — US-045 AC-5."""
    return {
        "label": nhan,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "retrieval_only": chi_truy_xuat,
        "models": {
            "embedding": f"{settings.embedding_model}@{settings.embedding_revision or 'unpinned'}",
            "rerank": f"{settings.rerank_model}@{settings.rerank_revision or 'unpinned'}",
            "generator": _ten_bo_sinh(),
            "judge": judge_model,
        },
        "config": {
            "retrieval_vector_enabled": settings.retrieval_vector_enabled,
            "retrieval_bm25_enabled": settings.retrieval_bm25_enabled,
            "retrieval_top_n_per_branch": settings.retrieval_top_n_per_branch,
            "rrf_k": settings.rrf_k,
            "rerank_enabled": settings.rerank_enabled,
            "rerank_candidates": settings.rerank_candidates,
            "rerank_top_k": settings.rerank_top_k,
            "tau": settings.tau,
            "contextual_retrieval_enabled": settings.contextual_retrieval_enabled,
            "verifier_enabled": settings.verifier_enabled,
            "chunk_tokens": settings.chunk_tokens,
            "chunk_overlap_ratio": settings.chunk_overlap_ratio,
            "llm_temperature": settings.llm_temperature,
        },
        "thresholds": NGUONG,
        "limitations": (
            []
            if judge_model not in _ten_bo_sinh()
            else [
                "Mô hình chấm TRÙNG mô hình sinh. US-045 AC-9 coi đây là hạn chế "
                "về phương pháp: một mô hình chấm chính câu nó vừa viết sẽ thiên "
                "vị theo hướng dễ đoán. Dùng --bo-cham với một mô hình khác."
            ]
        ),
    }


def doc_cau_hoi(so_cau: int | None = None) -> list[dict]:
    """Câu hỏi trong phạm vi, đã bỏ những câu người rà đã loại."""
    if not QUESTIONS.exists():
        print("Chưa có bộ câu hỏi. Chạy: python eval/build_dataset.py", file=sys.stderr)
        return []

    data = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    cau_hoi = [c for c in data["in_scope"] if c["review"]["status"] != "rejected"]

    chua_ra = sum(1 for c in cau_hoi if c["review"]["status"] == "pending")
    if chua_ra:
        print(f"[!] {chua_ra}/{len(cau_hoi)} câu CHƯA được người rà soát "
              f"(US-044 AC-6). Số liệu sinh ra chỉ dùng để thử đường ống.\n")

    # Cắt bớt phải lấy từ ĐẦU danh sách, không lấy ngẫu nhiên: hai cấu hình
    # ablation chạy trên hai tập con khác nhau thì không so được với nhau.
    return cau_hoi[:so_cau] if so_cau else cau_hoi


async def chay(
    *,
    nhan: str,
    chi_truy_xuat: bool = False,
    bo_cham: str | None = None,
    lam_lai: bool = False,
    so_cau: int | None = None,
    im_lang: bool = False,
) -> list[KetQua]:
    """Chạy một lượt đánh giá và trả về kết quả từng câu.

    Tách khỏi phần dòng lệnh để `eval/ablation.py` gọi lại được sáu lần với sáu
    cấu hình khác nhau, thay vì viết trùng cả vòng lặp.
    """
    cau_hoi = doc_cau_hoi(so_cau)
    if not cau_hoi:
        return []

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{nhan}.json"

    da_co: dict[str, dict] = {}
    if out.exists() and not lam_lai:
        cu = json.loads(out.read_text(encoding="utf-8"))
        da_co = {r["id"]: r for r in cu.get("results", [])}
        if da_co and not im_lang:
            print(f"Chạy tiếp: đã có {len(da_co)} kết quả trong {out.name}.")

    providers = (get_embedding_provider(), get_rerank_provider(), get_llm_provider())
    judge_model = bo_cham or settings.gemini_model
    judge = GeminiLLMProvider(model=judge_model)
    nhip_judge = Nhip(GOI_MOI_PHUT)

    if not im_lang:
        bo_sinh = _ten_bo_sinh()
        print(f"sinh  : {bo_sinh}")
        print(f"chấm  : {judge_model}"
              + ("  [!] TRÙNG bộ sinh" if judge_model in bo_sinh else ""))
        print(f"cấu hình: vector={settings.retrieval_vector_enabled} "
              f"bm25={settings.retrieval_bm25_enabled} rerank={settings.rerank_enabled} "
              f"τ={settings.tau} contextual={settings.contextual_retrieval_enabled} "
              f"verifier={settings.verifier_enabled}\n")

    with session_scope() as s:
        user = s.scalar(select(User).where(User.email == OWNER))
        if user is None:
            print("Chưa nạp tài liệu đánh giá.", file=sys.stderr)
            return []
        user_id = user.id
        nb_id = s.scalar(select(Notebook).where(Notebook.user_id == user.id)).id

    ket_qua: list[KetQua] = []
    for i, cau in enumerate(cau_hoi, 1):
        if cau["id"] in da_co:
            ket_qua.append(KetQua(**da_co[cau["id"]]))
            continue

        # Một phiên cho MỖI câu, không phải một phiên cho cả lượt chạy. Lượt
        # chạy kéo dài hàng giờ; giữ một kết nối mở suốt chừng ấy là để nó phơi
        # ra trước mọi thứ có thể cắt đứt, và đã có lần Docker tắt giữa chừng
        # làm mất trắng công việc.
        with session_scope() as s:
            kq = await chay_mot_cau(
                s, cau, nb_id, user_id, providers, judge, nhip_judge, chi_truy_xuat
            )
        ket_qua.append(kq)

        dau = "✓" if kq.dat else ("·" if chi_truy_xuat else "✗")
        print(f"[{i}/{len(cau_hoi)}] {dau} {kq.id} {kq.answer_kind:<10} "
              f"hạng={kq.context_rank or '—'} prec={kq.context_precision:.2f} "
              f"faith={kq.faithfulness if kq.faithfulness is not None else '—'} "
              f"cite={kq.citation_accuracy if kq.citation_accuracy is not None else '—'} "
              f"{kq.latency_ms}ms  {kq.nhom_loi}", flush=True)

        # Ghi sau MỖI câu — một lượt chạy đầy đủ trên CPU mất hàng giờ.
        _ghi(out, judge_model, nhan, chi_truy_xuat, ket_qua)

    _ghi(out, judge_model, nhan, chi_truy_xuat, ket_qua)
    return ket_qua


async def main_async(args: argparse.Namespace) -> int:
    ket_qua = await chay(
        nhan=args.nhan,
        chi_truy_xuat=args.chi_truy_xuat,
        bo_cham=args.bo_cham,
        lam_lai=args.lam_lai,
        so_cau=args.so_cau,
    )
    if not ket_qua:
        return 1
    _tom_tat(ket_qua)
    print(f"\nKết quả: {(RESULTS / f'{args.nhan}.json').relative_to(ROOT)}")
    return 0


def _ghi(
    out: Path, judge_model: str, nhan: str, chi_truy_xuat: bool, ket_qua: list[KetQua]
) -> None:
    out.write_text(
        json.dumps(
            {
                "metadata": _sieu_du_lieu(judge_model, nhan, chi_truy_xuat),
                "results": [asdict(k) for k in ket_qua],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


def _trung_binh(ket_qua: list[KetQua], ten: str) -> tuple[float | None, int]:
    gia_tri = [getattr(k, ten) for k in ket_qua if getattr(k, ten) is not None]
    if not gia_tri:
        return None, 0
    return sum(gia_tri) / len(gia_tri), len(gia_tri)


def _tom_tat(ket_qua: list[KetQua]) -> None:
    if not ket_qua:
        return

    print("\n" + "═" * 66)
    print(f"{'Chỉ số':<22}{'Trung bình':>12}{'Tối thiểu':>12}{'':>6}{'Đo được':>10}")
    print("─" * 66)
    for ten, nguong in NGUONG.items():
        tb, n = _trung_binh(ket_qua, ten)
        if tb is None:
            print(f"{ten:<22}{'—':>12}{nguong:>12.2f}{'':>6}{0:>10}")
            continue
        dat = "✓" if tb >= nguong else "✗"
        print(f"{ten:<22}{tb:>12.4f}{nguong:>12.2f}{dat:>6}{n:>10}/{len(ket_qua)}")

    # Hai chỉ số ghi lại để phân tích, KHÔNG dùng làm cổng — xem chú thích ở
    # `KetQua.citation_precision_gold`.
    print("─" * 66)
    for ten in ("citation_recall_gold", "citation_precision_gold"):
        tb, n = _trung_binh(ket_qua, ten)
        if tb is not None:
            print(f"{ten:<22}{tb:>12.4f}{'(tham khảo)':>18}{n:>10}/{len(ket_qua)}")

    dat = sum(1 for k in ket_qua if k.dat)
    print("─" * 66)
    print(f"{'pass rate toàn cục':<22}{dat / len(ket_qua):>12.1%}{'':>18}"
          f"{dat}/{len(ket_qua)}")

    tre = sorted(k.latency_ms for k in ket_qua)
    print(f"{'độ trễ trung vị':<22}{tre[len(tre) // 2]:>10} ms")
    print(f"{'độ trễ p95':<22}{tre[int(len(tre) * 0.95)]:>10} ms")

    truot = [k for k in ket_qua if k.nhom_loi]
    if truot:
        print("\nPhân loại lỗi (US-045 AC-7):")
        from collections import Counter
        for nhom, n in Counter(k.nhom_loi for k in truot).most_common():
            print(f"  {nhom:<24} {n:>4}  {n / len(ket_qua):>6.1%}")

    print("\nTheo loại câu hỏi (US-045 AC-8):")
    loai = sorted({k.type for k in ket_qua})
    for t in loai:
        nhom = [k for k in ket_qua if k.type == t]
        d = sum(1 for k in nhom if k.dat)
        rc, _ = _trung_binh(nhom, "context_recall")
        print(f"  {t:<16} {len(nhom):>4} câu · đạt {d / len(nhom):>5.1%} · "
              f"recall {rc:.2f}" if rc is not None else f"  {t:<16} {len(nhom):>4} câu")


def main() -> int:
    ap = argparse.ArgumentParser(description="Đo chất lượng hệ thống (US-045).")
    ap.add_argument("--nhan", default="mac-dinh", help="Tên lượt chạy, dùng làm tên tệp")
    ap.add_argument("--chi-truy-xuat", action="store_true",
                    help="Bỏ phần chấm bằng mô hình, chỉ đo truy xuất và trích dẫn")
    ap.add_argument("--bo-cham", default=None,
                    help="Mô hình chấm. Nên KHÁC mô hình sinh (US-045 AC-9)")
    ap.add_argument("--lam-lai", action="store_true",
                    help="Bỏ kết quả cũ, chạy lại từ đầu")
    ap.add_argument("--so-cau", type=int, default=None,
                    help="Chỉ chạy N câu đầu — để thử nhanh trên máy không có GPU")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
