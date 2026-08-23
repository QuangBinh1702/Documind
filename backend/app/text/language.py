"""Nhận diện ngôn ngữ câu hỏi — US-037.

Chỉ phân biệt **tiếng Việt và tiếng Anh**, vì đó là hai ngôn ngữ giao diện của
đồ án. Không dùng thư viện nhận diện ngôn ngữ tổng quát: chúng nặng, chúng đoán
sai trên câu ngắn, và bài toán ở đây hẹp hơn nhiều.

Vì sao không chỉ nhìn dấu
--------------------------
"Có dấu thì là tiếng Việt" đúng nhưng không đủ. Người Việt gõ **không dấu** rất
thường xuyên, và bộ đánh giá của đồ án đã đo được ảnh hưởng của việc đó lên
truy xuất (điểm rerank 0,2705 không dấu so với 0,9510 có dấu trên cùng một câu
hỏi). Nếu nhận diện ngôn ngữ cũng gãy ở đúng ca ấy thì người dùng gõ không dấu
sẽ nhận được câu trả lời bằng tiếng Anh — một lỗi hiển nhiên và khó chịu.

Nên có hai tầng: dấu tiếng Việt là bằng chứng dứt điểm; không có dấu thì đếm hư
từ, thứ khác nhau rõ giữa hai ngôn ngữ ngay cả khi đã bỏ dấu.

Hoà thì chọn tiếng Việt
------------------------
Đây là hệ thống hỏi đáp tài liệu tiếng Việt. Đoán nhầm sang tiếng Anh gây hại
nhiều hơn đoán nhầm sang tiếng Việt, nên tiếng Anh phải **thắng cách biệt** mới
được chọn.
"""

from __future__ import annotations

import re
from typing import Literal

__all__ = ["Language", "nhan_dien"]

Language = Literal["vi", "en"]

# Ký tự chỉ có trong tiếng Việt (và không có trong tiếng Anh). Một ký tự trong
# số này là đủ kết luận — không ngôn ngữ nào khác trong phạm vi đồ án dùng chúng.
_DAU_VIET = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯ]"
    r"|[àáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị]"
    r"|[òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]"
    r"|[ÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊ]"
    r"|[ÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ]"
)

# Hư từ và từ để hỏi, ở dạng ĐÃ BỎ DẤU — đây là tầng chạy khi không còn dấu để
# nhìn. Chọn những từ hiếm khi xuất hiện trong tiếng Anh.
_HU_TU_VIET = {
    "khong", "duoc", "nhung", "nao", "nguoi", "minh", "vay", "bao", "nhieu",
    "tai", "sao", "lam", "dau", "phai", "cua", "viec", "roi", "chua", "hoac",
    "cung", "moi", "neu", "thi", "boi", "cac", "gi", "ai", "day",
    "kia", "quy", "dinh", "theo", "trong", "voi", "tren", "duoi",
    "gom", "toi", "ban", "hay", "cho", "la", "co", "khi", "muon", "can",
}

_HU_TU_ANH = {
    "the", "is", "are", "was", "were", "what", "which", "who", "whom", "how",
    "why", "when", "where", "does", "do", "did", "can", "could", "should",
    "would", "of", "in", "on", "for", "with", "and", "or", "this", "that",
    "these", "those", "please", "tell", "explain", "about", "there", "their",
    "from", "have", "has", "been", "will", "not", "any", "all", "into",
}

# "the" trong tiếng Anh và "thế" tiếng Việt bỏ dấu trùng nhau. Những cụm này là
# tiếng Việt, không phải mạo từ.
_THE_VIET = re.compile(r"\bthe\s+(?:nao|gioi|ky|he|nhung|ma|thi)\b")

_TU = re.compile(r"[a-z]+")

# Tiếng Anh phải hơn cách biệt này mới được chọn — xem chú thích đầu tệp.
_CACH_BIET = 2


def nhan_dien(text: str) -> Language:
    """Ngôn ngữ của một câu hỏi. Trả về ``"vi"`` hoặc ``"en"``."""
    if not text or not text.strip():
        return "vi"

    if _DAU_VIET.search(text):
        return "vi"

    thap = text.lower()
    tu = set(_TU.findall(thap))

    diem_viet = len(tu & _HU_TU_VIET)
    diem_anh = len(tu & _HU_TU_ANH)

    if "the" in tu and _THE_VIET.search(thap):
        diem_anh -= 1
        diem_viet += 1

    return "en" if diem_anh - diem_viet >= _CACH_BIET else "vi"
