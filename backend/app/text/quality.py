"""Cổng chất lượng văn bản tiếng Việt — US-056.

Vì sao cần
----------
US-023 phân biệt PDF có text và PDF scan bằng cách đếm ký tự trên mỗi trang.
Cách đó bỏ sót trường hợp nguy hiểm nhất: **PDF có lớp text nhưng lớp đó hỏng**.

Ba dạng hỏng gặp trong thực tế với tài liệu tiếng Việt:

============  ===================================  ==========================
Dạng          Trông như thế nào                    Vì sao đếm ký tự không bắt
============  ===================================  ==========================
Bảng mã cũ    ``C¬ së d÷ liÖu``                    Đủ ký tự, nhưng là rác
Mất dấu       ``Co so du lieu``                    Đủ ký tự, mất thông tin
Mojibake      ``CÆ¡ sá»Ÿ dá»¯``                     Đủ ký tự, hỏng nặng
============  ===================================  ==========================

Cả ba đều **lập chỉ mục được mà không báo lỗi**, rồi làm hỏng mọi câu trả lời
về sau. Module này chấm điểm để chặn chúng trước khi vào kho tri thức.

Cách chấm
---------
Không thể chỉ đếm dấu tiếng Việt: một tài liệu tiếng Anh hợp lệ cũng có 0 dấu.
Nên trước hết phải đoán **văn bản này có định là tiếng Việt không**, bằng các
từ chức năng (``của``, ``và``, ``trong``, ``được``…). Nếu có, mới xét tiếp là
nó viết đúng dấu hay đã hỏng.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.text.normalize import VIETNAMESE_LETTERS, normalize, strip_accents

__all__ = ["LegacyEncoding", "TextQuality", "assess"]

LegacyEncoding = Literal["tcvn3", "vni"] | None

# Từ chức năng tiếng Việt — xuất hiện dày trong mọi văn bản tiếng Việt bất kể
# chủ đề. Dùng dạng KHÔNG DẤU để nhận ra cả văn bản đã mất dấu.
# fmt: off
_VI_FUNCTION_WORDS = frozenset([
    "cua", "va", "la", "trong", "duoc", "co", "khong", "cho", "den", "tu",
    "voi", "nhung", "nay", "do", "khi", "neu", "thi", "ma", "cac", "mot",
    "nguoi", "phai", "se", "da", "dang", "cung", "theo", "tren", "duoi",
    "truoc", "sau", "tai", "ve", "boi", "vi", "nen", "ra", "vao",
])
# fmt: on

# Ký tự thuộc khối ký hiệu Latin-1 (U+00A1–U+00BF): § ¹ ¸ ¬ µ ® « » ° ± ...
# Trong văn bản bình thường chúng gần như không bao giờ nằm *bên trong* một từ.
# Trong TCVN3/ABC thì gần như mọi từ có dấu đều chứa một ký tự như vậy.
_SYMBOL_CHARS = re.compile(r"[¡-¿]")

# VNI dùng các chữ cái này thay cho dấu, đặc biệt 'ñ' cho 'đ'. Trong tiếng Việt
# và tiếng Anh đúng chuẩn, tần suất của chúng bằng không.
_VNI_CHARS = re.compile(r"[ñöøÑÖØ]")

# Từ (theo nghĩa rộng, cho phép ký hiệu lẫn vào) để đếm tỉ lệ từ bị nhiễm.
_LOOSE_WORD = re.compile(r"\S+")

# Tỉ lệ TỪ chứa ký hiệu lạ. Đây mới là tín hiệu phân biệt được, thay vì tỉ lệ
# trên tổng số ký tự: một tài liệu có vài chỗ "25°C" hay "±5%" chỉ đạt vài phần
# trăm, trong khi văn bản TCVN3 vượt xa ngưỡng này.
_LEGACY_WORD_RATIO = 0.15

# Dấu hiệu mojibake: chuỗi UTF-8 bị đọc như Latin-1.
_MOJIBAKE = re.compile(r"Ã[-¿]|Â[ -¿]|á»|Æ°|áº")

_HTML_ENTITY = re.compile(r"&(?:[a-zA-Z]{2,10}|#\d{2,5}|#x[0-9a-fA-F]{2,6});")

# Token lẫn lộn chữ và số kiểu "l0ai" hoặc "5945abc" — dấu hiệu OCR sai.
_WEIRD_ALNUM = re.compile(r"\b(?=\w*[a-zA-ZÀ-ỹ])(?=\w*\d)\w{4,}\b")

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass(frozen=True)
class TextQuality:
    """Kết quả chấm điểm. `score` nằm trong [0, 1], càng cao càng tốt."""

    score: float
    looks_vietnamese: bool
    diacritic_ratio: float
    legacy_encoding: LegacyEncoding
    mojibake_ratio: float
    replacement_ratio: float
    html_entity_count: int
    weird_alnum_ratio: float
    letter_ratio: float
    char_count: int
    issues: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """Có nên lập chỉ mục văn bản này không.

        Ngưỡng lấy từ `settings.text_quality_min`; ở đây chỉ trả về điểm để
        tầng gọi so sánh — module này không đọc cấu hình.
        """
        return self.legacy_encoding is None and self.replacement_ratio < 0.01


def assess(text: str) -> TextQuality:
    """Chấm chất lượng một đoạn văn bản đã trích xuất.

    Hàm thuần, không phụ thuộc cấu hình hay I/O — nhờ vậy test được trực tiếp.
    """
    text = normalize(text)
    n = len(text)
    if n == 0:
        return TextQuality(
            score=0.0,
            looks_vietnamese=False,
            diacritic_ratio=0.0,
            legacy_encoding=None,
            mojibake_ratio=0.0,
            replacement_ratio=0.0,
            html_entity_count=0,
            weird_alnum_ratio=0.0,
            letter_ratio=0.0,
            char_count=0,
            issues=["văn bản rỗng"],
        )

    issues: list[str] = []
    words = _WORD.findall(text)
    letters = [c for c in text if c.isalpha()]
    letter_ratio = len(letters) / n

    # ── Có phải tiếng Việt không ────────────────────────
    # So khớp bằng dạng không dấu để nhận ra cả văn bản đã bị mất dấu.
    bare = strip_accents(text).lower()
    bare_words = _WORD.findall(bare)
    fn_hits = sum(1 for w in bare_words if w in _VI_FUNCTION_WORDS)
    fn_ratio = fn_hits / len(bare_words) if bare_words else 0.0
    looks_vietnamese = fn_ratio >= 0.04 and len(bare_words) >= 20

    diacritics = sum(1 for c in letters if c in VIETNAMESE_LETTERS)
    diacritic_ratio = diacritics / len(letters) if letters else 0.0

    # ── Bảng mã cũ ──────────────────────────────────────
    #
    # Đo theo TỈ LỆ TỪ bị nhiễm, không theo tỉ lệ ký tự. Lý do: văn bản TCVN3
    # nhiễm gần như mọi từ có dấu, trong khi một tài liệu hợp lệ có vài chỗ
    # "25°C" chỉ đạt vài phần trăm. Cũng KHÔNG dùng "ít dấu tiếng Việt" làm
    # điều kiện — rác TCVN3 tình cờ chứa những ký tự vốn là chữ tiếng Việt hợp
    # lệ (è, ô, µ…), nên tỉ lệ dấu của nó không hề bằng không.
    legacy: LegacyEncoding = None
    loose_words = _LOOSE_WORD.findall(text)
    n_words = len(loose_words) or 1

    tcvn3_words = sum(1 for w in loose_words if _SYMBOL_CHARS.search(w))
    vni_words = sum(1 for w in loose_words if _VNI_CHARS.search(w))
    tcvn3_ratio = tcvn3_words / n_words
    vni_ratio = vni_words / n_words

    if tcvn3_ratio >= _LEGACY_WORD_RATIO:
        legacy = "tcvn3"
        issues.append(
            f"Nghi bảng mã TCVN3/ABC: {tcvn3_ratio:.0%} số từ chứa ký hiệu lạ "
            f"({tcvn3_words}/{n_words} từ) — văn bản này là rác, không phải nội dung"
        )
    elif vni_ratio >= _LEGACY_WORD_RATIO:
        legacy = "vni"
        issues.append(
            f"Nghi bảng mã VNI-Windows: {vni_ratio:.0%} số từ chứa ñ/ö/ø "
            f"({vni_words}/{n_words} từ)"
        )

    # ── Hỏng mã hoá ─────────────────────────────────────
    mojibake = len(_MOJIBAKE.findall(text))
    mojibake_ratio = mojibake / n
    if mojibake_ratio > 0.001:
        issues.append(f"Có dấu hiệu mojibake (UTF-8 bị đọc như Latin-1): {mojibake} chỗ")

    replacement = text.count("�")
    replacement_ratio = replacement / n
    if replacement:
        issues.append(f"Có {replacement} ký tự thay thế U+FFFD — mã hoá đã hỏng")

    html_entities = len(_HTML_ENTITY.findall(text))
    if html_entities > 3:
        issues.append(f"Còn sót {html_entities} HTML entity chưa giải mã")

    weird = len(_WEIRD_ALNUM.findall(text))
    weird_ratio = weird / len(words) if words else 0.0
    if weird_ratio > 0.03:
        issues.append(
            f"{weird_ratio:.1%} token lẫn lộn chữ và số — thường là dấu hiệu OCR sai"
        )

    # ── Mất dấu ─────────────────────────────────────────
    if looks_vietnamese and legacy is None and diacritic_ratio < 0.03:
        issues.append(
            "Văn bản có dạng tiếng Việt nhưng gần như không có dấu — "
            "có thể đã bị mất dấu khi trích xuất"
        )

    if letter_ratio < 0.35:
        issues.append(
            f"Chỉ {letter_ratio:.0%} ký tự là chữ cái — có thể là bảng biểu, "
            f"mục lục, hoặc trang gần như rỗng"
        )

    score = _score(
        looks_vietnamese=looks_vietnamese,
        diacritic_ratio=diacritic_ratio,
        legacy=legacy,
        mojibake_ratio=mojibake_ratio,
        replacement_ratio=replacement_ratio,
        weird_ratio=weird_ratio,
        letter_ratio=letter_ratio,
    )

    return TextQuality(
        score=score,
        looks_vietnamese=looks_vietnamese,
        diacritic_ratio=diacritic_ratio,
        legacy_encoding=legacy,
        mojibake_ratio=mojibake_ratio,
        replacement_ratio=replacement_ratio,
        html_entity_count=html_entities,
        weird_alnum_ratio=weird_ratio,
        letter_ratio=letter_ratio,
        char_count=n,
        issues=issues,
    )


def _score(
    *,
    looks_vietnamese: bool,
    diacritic_ratio: float,
    legacy: LegacyEncoding,
    mojibake_ratio: float,
    replacement_ratio: float,
    weird_ratio: float,
    letter_ratio: float,
) -> float:
    """Gộp các tín hiệu thành một điểm trong [0, 1].

    Bảng mã cũ và ký tự thay thế bị phạt nặng vì chúng làm văn bản **không dùng
    được**, không phải chỉ kém chất lượng.
    """
    if legacy is not None:
        return 0.05
    if replacement_ratio > 0.02:
        return 0.10

    score = 1.0
    score -= min(0.45, mojibake_ratio * 300)
    score -= min(0.30, replacement_ratio * 400)
    score -= min(0.20, max(0.0, weird_ratio - 0.02) * 4)

    if letter_ratio < 0.35:
        score -= (0.35 - letter_ratio) * 1.2

    # Chỉ phạt thiếu dấu khi văn bản trông đúng là tiếng Việt. Một tài liệu
    # tiếng Anh hợp lệ có 0 dấu và không đáng bị phạt.
    if looks_vietnamese:
        if diacritic_ratio < 0.03:
            score -= 0.55
        elif diacritic_ratio < 0.08:
            score -= 0.25

    return max(0.0, min(1.0, score))
