"""Chuẩn hoá văn bản — RANH GIỚI DUY NHẤT của hệ thống.

Bất biến INV-2 (`SPEC-v1.md` §1.3): mọi chuỗi đi vào cơ sở dữ liệu đều đã qua
`normalize()` ở đây, và **không nơi nào khác được gọi `unicodedata.normalize`**.

Vì sao phải có một ranh giới duy nhất
-------------------------------------
Tiếng Việt biểu diễn được hai cách trong Unicode: `"ế"` là **một** codepoint
(U+1EBF, dạng NFC) hoặc **ba** codepoint (`e` + U+0302 + U+0301, dạng NFD).
Văn bản từ macOS, một số PDF và một phần đầu ra OCR trả về NFD.

Nếu hai dạng cùng tồn tại trong hệ thống thì:

* độ dài chuỗi khác nhau → **mọi `char_start`/`char_end` lệch** (hỏng INV-1);
* so khớp chuỗi `snippet` để tô sáng thất bại **không báo lỗi**;
* `to_tsvector` sinh token khác nhau → nhánh từ khoá không khớp;
* embedding của cùng một câu ra hai vector khác nhau.

Toàn bộ các lỗi trên đều **im lặng**. Đó là lý do chuẩn hoá phải xảy ra đúng
một lần, tại một chỗ, ngay khi văn bản vừa được trích ra — trước khi bất kỳ
offset nào được tính.

Thứ tự thao tác
---------------
Dọn dẹp trước, NFC sau. Nhờ vậy đầu ra **luôn** ở dạng NFC, kể cả khi việc dọn
dẹp tạo ra tổ hợp mới (ví dụ `e` + ZWSP + dấu sắc → xoá ZWSP → NFC → `é`).
"""

from __future__ import annotations

import re
import unicodedata

__all__ = [
    "VIETNAMESE_LETTERS",
    "is_normalized",
    "normalize",
    "strip_accents",
]

# Ký tự vô hình: không hiển thị nhưng vẫn tính vào độ dài chuỗi, nên chúng làm
# lệch offset và phá so khớp chuỗi. PDF và trình soạn thảo rắc chúng khắp nơi.
_INVISIBLE = re.compile(
    "["
    "​"  # ZERO WIDTH SPACE
    "‌"  # ZERO WIDTH NON-JOINER
    "‍"  # ZERO WIDTH JOINER
    "⁠"  # WORD JOINER
    "﻿"  # BOM / ZERO WIDTH NO-BREAK SPACE
    "­"  # SOFT HYPHEN — PDF dùng để ngắt dòng, không phải nội dung
    "]"
)

# Các loại khoảng trắng lạ. Gom hết về dấu cách thường để so khớp chuỗi đoán
# được. Không gộp nhiều dấu cách thành một — việc đó thuộc bước làm sạch của
# trình trích xuất, không phải của chuẩn hoá.
_ODD_SPACES = re.compile(
    "["
    " "  # NO-BREAK SPACE
    "  - "  # các dấu cách in ấn
    " "  # NARROW NO-BREAK SPACE
    " "  # MEDIUM MATHEMATICAL SPACE
    "　"  # IDEOGRAPHIC SPACE
    "]"
)

# Ký tự điều khiển C0/C1, trừ \n và \t. Chúng không bao giờ là nội dung.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# Chữ cái riêng của tiếng Việt: nguyên âm có dấu phụ và chữ đ.
# Dùng để nhận biết văn bản có thực sự là tiếng Việt hay không (xem quality.py).
VIETNAMESE_LETTERS = frozenset(
    "àáảãạăằắẳẵặâầấẩẫậ"
    "èéẻẽẹêềếểễệ"
    "ìíỉĩị"
    "òóỏõọôồốổỗộơờớởỡợ"
    "ùúủũụưừứửữự"
    "ỳýỷỹỵ"
    "đ"
    "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬ"
    "ÈÉẺẼẸÊỀẾỂỄỆ"
    "ÌÍỈĨỊ"
    "ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢ"
    "ÙÚỦŨỤƯỪỨỬỮỰ"
    "ỲÝỶỸỴ"
    "Đ"
)


def normalize(raw: str) -> str:
    """Đưa văn bản về dạng chuẩn của hệ thống.

    Idempotent: ``normalize(normalize(s)) == normalize(s)``.

    Thao tác, theo đúng thứ tự:

    1. thống nhất xuống dòng ``\\r\\n`` và ``\\r`` thành ``\\n``;
    2. bỏ ký tự điều khiển (giữ ``\\n`` và ``\\t``);
    3. bỏ ký tự vô hình và dấu gạch nối mềm;
    4. đổi mọi loại khoảng trắng lạ thành dấu cách thường;
    5. chuẩn hoá Unicode về **NFC**.

    Mọi bước đều có thể đổi độ dài chuỗi. Vì vậy hàm này phải chạy **trước** khi
    tính bất kỳ offset nào, và kết quả của nó là chuỗi mà `char_start`/`char_end`
    tham chiếu tới (`source_texts.full_text`).
    """
    if not raw:
        return ""

    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = _INVISIBLE.sub("", text)
    text = _ODD_SPACES.sub(" ", text)
    return unicodedata.normalize("NFC", text)


def is_normalized(text: str) -> bool:
    """Kiểm tra một chuỗi đã ở dạng chuẩn chưa.

    Dùng trong assertion và test, không dùng trên đường xử lý chính — ở đó cứ
    gọi thẳng `normalize()` vì nó idempotent.
    """
    return text == normalize(text)


# Bảng bỏ dấu. Không dùng trên đường lưu trữ — chỉ dùng cho các phép so sánh
# không phân biệt dấu ở tầng ứng dụng. Nhánh từ khoá đã có `unaccent` của
# PostgreSQL lo việc này rồi.
_ACCENT_MAP = str.maketrans(
    {
        **{c: "a" for c in "àáảãạăằắẳẵặâầấẩẫậ"},
        **{c: "A" for c in "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬ"},
        **{c: "e" for c in "èéẻẽẹêềếểễệ"},
        **{c: "E" for c in "ÈÉẺẼẸÊỀẾỂỄỆ"},
        **{c: "i" for c in "ìíỉĩị"},
        **{c: "I" for c in "ÌÍỈĨỊ"},
        **{c: "o" for c in "òóỏõọôồốổỗộơờớởỡợ"},
        **{c: "O" for c in "ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢ"},
        **{c: "u" for c in "ùúủũụưừứửữự"},
        **{c: "U" for c in "ÙÚỦŨỤƯỪỨỬỮỰ"},
        **{c: "y" for c in "ỳýỷỹỵ"},
        **{c: "Y" for c in "ỲÝỶỸỴ"},
        "đ": "d",
        "Đ": "D",
    }
)


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt, giữ nguyên độ dài chuỗi.

    Giữ nguyên độ dài là điểm quan trọng: nhờ vậy có thể so sánh không dấu mà
    offset vẫn ánh xạ được về chuỗi gốc.
    """
    return normalize(text).translate(_ACCENT_MAP)
