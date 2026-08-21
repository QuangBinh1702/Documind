"""Tách câu và tách từ tiếng Việt.

Hai hàm ở đây phục vụ hai đường khác nhau, và điểm khác biệt đó rất quan trọng:

``split_sentences`` — **đường lập chỉ mục**
    Trả về **khoảng offset**, không phải chuỗi. US-008 AC-2 yêu cầu ranh giới
    chunk rơi vào ranh giới câu, mà chunk lại phải mang `char_start`/`char_end`
    đúng (INV-1). Nếu hàm tách câu trả về chuỗi rồi mã gọi phải đi tìm lại vị
    trí của chuỗi đó trong văn bản gốc, đó chính là cách offset lệch — chuỗi
    lặp lại sẽ tìm ra sai chỗ. Nên hàm này **không bao giờ** trả về chuỗi.

``segment_words`` — **đường truy vấn**
    Chỉ dùng để dựng `tsquery` (US-010 AC-2b). Theo quyết định 0001, đường lập
    chỉ mục **không** tách từ, nên nếu tách từ ở đây sai thì hậu quả chỉ là một
    truy vấn kém tối ưu, không phải một chỉ mục rác tồn tại vĩnh viễn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from app.text.normalize import normalize, strip_accents

__all__ = ["Span", "build_tsquery_parts", "segment_words", "split_sentences"]


@dataclass(frozen=True, slots=True)
class Span:
    """Một khoảng nửa mở ``[start, end)`` trên văn bản đã chuẩn hoá."""

    start: int
    end: int

    def slice(self, text: str) -> str:
        return text[self.start : self.end]

    def __len__(self) -> int:
        return self.end - self.start


# ── Viết tắt tiếng Việt ────────────────────────────────
#
# Dấu chấm sau những từ này KHÔNG kết thúc câu. Danh sách tập trung vào văn bản
# học thuật và hành chính — hai loại tài liệu chính của đồ án.
# fmt: off
_ABBREVIATIONS = frozenset([
    # học hàm, học vị
    "ts", "pgs", "gs", "ths", "bs", "ks", "cn", "ncs",
    # xưng hô
    "ông", "bà", "anh", "chị", "em", "cô", "chú", "bác",
    # đơn vị hành chính
    "tp", "q", "p", "h", "x", "tt", "ttp",
    # loại văn bản
    "đ", "kh", "k", "nđ", "qđ", "cv", "bc", "ttr", "nq", "ct",
    # tiêu chuẩn
    "tcvn", "iso", "iec", "ieee",
    # thông dụng
    "tr", "st", "stt", "vd", "vv", "v.v", "no", "nr", "vol", "fig",
])
# fmt: on

# Chữ số La Mã — "Chương II." không kết thúc câu nếu sau đó là tiêu đề.
_ROMAN = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)

# Ứng viên kết thúc câu: dấu chấm/hỏi/than/ba chấm, có thể kèm ngoặc đóng,
# theo sau là khoảng trắng.
_CANDIDATE = re.compile(r'([.!?…]+)(["\'”’)\]]*)(\s+)')

# Từ đứng ngay trước dấu chấm.
_PREV_WORD = re.compile(r"([^\s.]+)\.?$")


def _is_sentence_end(text: str, dot_pos: int, next_pos: int) -> bool:
    """Dấu chấm ở `dot_pos` có thật sự kết thúc câu không?"""
    before = text[:dot_pos]
    after = text[next_pos:]

    if not after:
        return True

    prev = _PREV_WORD.search(before)
    if prev:
        token = prev.group(1)
        lowered = token.lower().rstrip(".")

        # "TS. Nguyễn", "TP. Đà Nẵng", "v.v."
        if lowered in _ABBREVIATIONS:
            return False

        # Một chữ cái đơn — chữ viết tắt tên riêng: "Nguyễn V. A."
        if len(token) == 1 and token.isalpha():
            return False

        # "Chương II." theo sau bởi chữ hoa vẫn có thể là tiêu đề, nhưng ta
        # chấp nhận cắt ở đây: tiêu đề thành một "câu" riêng là hợp lý.
        if _ROMAN.match(lowered) and after[:1].islower():
            return False

        # Số thứ tự: "Điều 5." hoặc "1." đứng đầu mục. Nếu sau đó là chữ
        # thường thì chưa hết câu; nếu là chữ hoa thì coi như hết.
        if lowered.isdigit() and after[:1].islower():
            return False

    # Số thập phân và số hiệu: "5.2", "5945:2005", "1.000.000"
    if text[dot_pos - 1 : dot_pos].isdigit() and after[:1].isdigit():
        return False

    # Câu mới thường bắt đầu bằng chữ hoa, chữ số, hoặc dấu mở ngoặc/gạch đầu dòng.
    first = after[0]
    return first.isupper() or first.isdigit() or first in "\"'“‘(-–—•"


def split_sentences(text: str) -> list[Span]:
    """Tách văn bản thành các câu, trả về **khoảng offset**.

    Bảo đảm:

    * các khoảng không chồng nhau và tăng dần;
    * ghép lại đúng bằng văn bản gốc, kể cả khoảng trắng — nói cách khác
      ``"".join(s.slice(t) for s in split_sentences(t)) == t``;
    * khoảng trắng cuối câu thuộc về câu đứng trước, để không có ký tự nào rơi
      ra ngoài mọi khoảng.

    Bảo đảm thứ hai là điều làm hàm này an toàn cho INV-1: không ký tự nào bị
    mất, nên chunker ghép các câu lại luôn ra offset đúng.
    """
    text = normalize(text)
    if not text:
        return []

    spans: list[Span] = []
    start = 0

    for m in _CANDIDATE.finditer(text):
        dot_pos = m.start(1)
        next_pos = m.end(3)  # sau dấu câu, ngoặc đóng và khoảng trắng

        if not _is_sentence_end(text, dot_pos, next_pos):
            continue

        # Khoảng trắng gộp vào câu trước để không ký tự nào bị bỏ rơi.
        spans.append(Span(start, next_pos))
        start = next_pos

    if start < len(text):
        spans.append(Span(start, len(text)))

    return [s for s in spans if s.start < s.end]


# ── Tách từ (chỉ dùng cho đường truy vấn) ──────────────


@lru_cache(maxsize=1)
def _underthesea_tokenizer():  # pragma: no cover - phụ thuộc môi trường
    """Nạp underthesea nếu có. Không có thì trả None và ta xuống phương án dự phòng."""
    try:
        from underthesea import word_tokenize

        return word_tokenize
    except Exception:
        return None


def segment_words(text: str) -> list[str]:
    """Tách câu hỏi thành token, từ ghép nối bằng dấu gạch dưới.

    Ví dụ: ``"chuẩn hoá cơ sở dữ liệu"`` → ``["chuẩn_hoá", "cơ_sở_dữ_liệu"]``.

    Nếu không có ``underthesea``, mỗi từ đứng riêng. Hệ thống vẫn chạy, chỉ là
    truy vấn kém chính xác hơn với cụm từ ghép — suy giảm êm, không sập.
    """
    text = normalize(text).strip()
    if not text:
        return []

    tokenize = _underthesea_tokenizer()
    if tokenize is None:
        return [w for w in re.split(r"\s+", text) if w]

    try:
        return [t.replace(" ", "_") for t in tokenize(text) if t.strip()]
    except Exception:
        return [w for w in re.split(r"\s+", text) if w]


# Ký tự không mang nghĩa tìm kiếm. Giữ lại chữ, số, gạch dưới, gạch ngang,
# dấu hai chấm và chấm — chúng nằm trong mã hiệu văn bản kiểu "TCVN 5945:2005".
_QUERY_NOISE = re.compile(r"[^\w\s:.\-/]", re.UNICODE)

# Từ dừng tiếng Việt cho đường TRUY VẤN.
#
# Không dùng khi lập chỉ mục — chỉ mục giữ nguyên mọi từ. Ở đây chúng bị loại
# vì các mảnh truy vấn được nối bằng OR: giữ lại "được", "theo", "nào" thì
# gần như mọi chunk trong notebook đều khớp và thứ hạng mất hết ý nghĩa.
#
# So khớp ở dạng KHÔNG DẤU để bắt cả câu hỏi người dùng gõ thiếu dấu.
# fmt: off
_VI_STOPWORDS = frozenset([
    "la", "va", "cua", "co", "duoc", "cho", "voi", "trong", "tren", "duoi",
    "den", "tu", "theo", "boi", "vi", "nen", "ra", "vao", "ve", "tai",
    "nay", "do", "kia", "ay", "nao", "gi", "sao", "dau", "ai",
    "mot", "cac", "nhung", "moi", "ca",
    # Loại từ chỉ loại, không mang nội dung. KHÔNG đưa "điều", "khoản",
    # "chương" vào đây — trong văn bản pháp quy chúng là từ khoá thật.
    "cai", "chiec", "viec",
    "thi", "ma", "neu", "khi", "de", "hay", "hoac", "nhung_ma",
    "se", "da", "dang", "cung", "van", "con", "chi", "deu",
    "khong", "chua", "phai", "can", "nen_lam",
    "toi", "ban", "minh", "ho", "no",
    "the", "nhu", "rang", "a", "u", "o",
])
# fmt: on


def build_tsquery_parts(question: str) -> list[tuple[str, str]]:
    """Chuẩn bị các mảnh để dựng ``tsquery`` theo quyết định 0001.

    Trả về danh sách ``(loại, nội_dung)`` với ``loại`` là ``"phrase"`` hoặc
    ``"plain"``. Tầng repository ghép chúng bằng ``&&``:

        phraseto_tsquery('vi', 'cơ sở dữ liệu') && plainto_tsquery('vi', 'chuẩn')

    Cụm từ ghép dùng ``phraseto_tsquery`` để yêu cầu các âm tiết **liền kề** —
    nhờ vậy tài liệu *"cơ sở vật chất và dữ liệu thống kê"* không khớp truy vấn
    *"cơ sở dữ liệu"*, điều mà truy vấn AND thường làm sai.
    """
    cleaned = _QUERY_NOISE.sub(" ", normalize(question))
    parts: list[tuple[str, str]] = []
    dropped: list[tuple[str, str]] = []

    for token in segment_words(cleaned):
        token = token.strip("_-:./")
        if not token:
            continue

        part = (
            ("phrase", token.replace("_", " ")) if "_" in token else ("plain", token)
        )

        # Từ ghép luôn được giữ: chúng mang nghĩa kể cả khi từng âm tiết là từ
        # dừng. Chỉ lọc từ đơn.
        if part[0] == "plain" and strip_accents(token).lower() in _VI_STOPWORDS:
            dropped.append(part)
        else:
            parts.append(part)

    # Câu hỏi toàn từ dừng ("cái này là gì?") thì thà tìm bằng chúng còn hơn
    # không tìm gì. Nhánh vector sẽ gánh phần còn lại.
    return parts or dropped
