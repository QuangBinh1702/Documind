"""Cổng chất lượng văn bản tiếng Việt — US-056.

Ba ca bắt buộc theo AC-5: văn bản sạch (điểm cao), mojibake (điểm thấp), và
văn bản tiếng Anh thuần (không bị phạt oan vì không có dấu tiếng Việt).
"""

from __future__ import annotations

from app.text.quality import assess

# Văn bản pháp quy tiếng Việt viết đúng chuẩn.
CLEAN_VI = """
Điều 5. Phạm vi áp dụng của quy chế này bao gồm toàn bộ hoạt động đào tạo
trình độ đại học tại các cơ sở giáo dục. Người học được cấp bằng khi hoàn
thành chương trình và đạt chuẩn đầu ra theo quy định. Trong trường hợp có
thay đổi, nhà trường phải thông báo cho người học trước ít nhất ba mươi ngày.
Các đơn vị trực thuộc có trách nhiệm triển khai và báo cáo kết quả thực hiện.
"""

# Cùng nội dung nhưng đã bị mất dấu — thường gặp khi trích xuất PDF sai font.
STRIPPED_VI = """
Dieu 5. Pham vi ap dung cua quy che nay bao gom toan bo hoat dong dao tao
trinh do dai hoc tai cac co so giao duc. Nguoi hoc duoc cap bang khi hoan
thanh chuong trinh va dat chuan dau ra theo quy dinh. Trong truong hop co
thay doi, nha truong phai thong bao cho nguoi hoc truoc it nhat ba muoi ngay.
Cac don vi truc thuoc co trach nhiem trien khai va bao cao ket qua thuc hien.
"""

# UTF-8 bị đọc như Latin-1.
MOJIBAKE = """
Ãiá»u 5. Pháº¡m vi Ã¡p dá»¥ng cá»§a quy cháº¿ nÃ y bao gá»m toÃ n bá»
hoáº¡t Ä'á»™ng Ä'Ã o táº¡o trÃ¬nh Ä'á»™ Ä'áº¡i há»c táº¡i cÃ¡c cÆ¡ sá»Ÿ
giÃ¡o dá»¥c. NgÆ°á»i há»c Ä'Æ°á»£c cáº¥p báº±ng khi hoÃ n thÃ nh.
"""

# Bảng mã TCVN3/ABC đọc như CP1252 — ký hiệu nằm ngay giữa chữ.
TCVN3 = """
§iÒu 5. Ph¹m vi ¸p dông cña quy chÕ nµy bao gåm toµn bé ho¹t ®éng ®µo t¹o
tr×nh ®é ®¹i häc t¹i c¸c c¬ së gi¸o dôc. Ng­êi häc ®­îc cÊp b»ng khi hoµn
thµnh ch­¬ng tr×nh vµ ®¹t chuÈn ®Çu ra theo quy ®Þnh cña nhµ tr­êng.
"""

# Tiếng Anh hợp lệ — không có dấu tiếng Việt, nhưng KHÔNG được coi là kém.
CLEAN_EN = """
Article 5. The scope of this regulation covers all training activities at the
undergraduate level in higher education institutions. Learners are awarded a
degree upon completing the programme and meeting the stated learning outcomes.
Should any change occur, the institution must notify learners at least thirty
days in advance. Affiliated units are responsible for implementation.
"""


def test_van_ban_tieng_viet_sach_diem_cao() -> None:
    q = assess(CLEAN_VI)
    assert q.looks_vietnamese
    assert q.legacy_encoding is None
    assert q.diacritic_ratio > 0.10
    assert q.score >= 0.85, f"điểm {q.score}, vấn đề: {q.issues}"
    assert q.usable


def test_tieng_anh_khong_bi_phat_oan() -> None:
    """Không có dấu tiếng Việt là bình thường với tiếng Anh — đây là lý do phải
    đoán "văn bản này có định là tiếng Việt không" trước khi xét dấu."""
    q = assess(CLEAN_EN)
    assert not q.looks_vietnamese
    assert q.diacritic_ratio == 0.0
    assert q.score >= 0.85, f"tiếng Anh bị phạt oan: {q.score}, {q.issues}"
    assert q.usable


def test_mat_dau_bi_phat() -> None:
    """Trông đúng là tiếng Việt nhưng gần như không có dấu — chỉ dấu của việc
    trích xuất sai font."""
    q = assess(STRIPPED_VI)
    assert q.looks_vietnamese, "phải nhận ra đây là tiếng Việt qua từ chức năng"
    assert q.diacritic_ratio < 0.03
    assert q.score < 0.60, f"điểm {q.score} — lẽ ra phải bị phạt"
    assert any("mất dấu" in i for i in q.issues)


def test_mojibake_diem_thap() -> None:
    q = assess(MOJIBAKE)
    assert q.score < 0.60, f"điểm {q.score}, vấn đề: {q.issues}"
    assert q.mojibake_ratio > 0


def test_phat_hien_bang_ma_tcvn3() -> None:
    """Ca nguy hiểm nhất: đủ ký tự nên US-023 đếm ký tự không bắt được, nhưng
    nội dung là rác hoàn toàn."""
    q = assess(TCVN3)
    assert q.legacy_encoding == "tcvn3", f"không nhận ra TCVN3: {q}"
    assert q.score <= 0.10
    assert not q.usable
    assert any("TCVN3" in i for i in q.issues)


def test_ky_tu_thay_the_lam_khong_dung_duoc() -> None:
    q = assess("Cơ sở dữ liệu " + "�" * 30)
    assert q.replacement_ratio > 0
    assert not q.usable


def test_van_ban_rong() -> None:
    q = assess("")
    assert q.score == 0.0
    assert q.char_count == 0
    assert q.issues


def test_ky_hieu_hop_le_lac_vao_khong_bi_bao_nham_bang_ma_cu() -> None:
    """Bộ dò đo TỈ LỆ TỪ bị nhiễm, nên vài chỗ "25°C" hay "±5%" trong một tài
    liệu bình thường không đủ để bị kết luận là bảng mã cũ."""
    text = (
        CLEAN_VI
        + " Nhiệt độ nước thải không vượt quá 40°C và sai số cho phép là ±5%. "
        + "Diện tích tối thiểu là 25m² cho mỗi phòng học theo quy định hiện hành."
    )
    q = assess(text)
    assert q.legacy_encoding is None, f"báo nhầm: {q.issues}"
    assert q.usable


def test_diem_luon_trong_khoang_hop_le() -> None:
    for sample in [CLEAN_VI, CLEAN_EN, STRIPPED_VI, MOJIBAKE, TCVN3, "", "x", "123 456"]:
        q = assess(sample)
        assert 0.0 <= q.score <= 1.0


def test_van_ban_sach_hon_thi_diem_cao_hon() -> None:
    """Quan hệ thứ tự quan trọng hơn giá trị tuyệt đối — ngưỡng còn hiệu chỉnh."""
    assert assess(CLEAN_VI).score > assess(STRIPPED_VI).score
    assert assess(STRIPPED_VI).score > assess(TCVN3).score
