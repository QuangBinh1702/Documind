# Xuất xứ tài liệu kiểm thử

Ghi lại **ngay khi tải**, không để dồn. Bảng này vào phụ lục báo cáo và trả lời
câu hỏi về nguồn gốc dữ liệu khi bảo vệ (US-044 AC-7).

Tệp gốc **không commit** — `eval/dataset/documents/` nằm trong `.gitignore`.
Bảng này là thứ duy nhất được lưu, và nó đủ để người khác tải lại đúng bộ dữ liệu.

## Nguyên tắc chọn

Chỉ dùng **văn bản công khai**: pháp quy, quy chế, thông tư, quyết định, tài
liệu mở. Không đưa giáo trình có bản quyền vào bộ kiểm thử — xem
`docs/CHUAN-BI-DU-LIEU.md` §3.

## Danh mục

| # | Tệp | Nguồn | Ngày tải | Trang | Loại | Ghi chú |
|---|---|---|---|---|---|---|
| 1 | | | | | | |

*Cột **Loại**: `text` (PDF có lớp text) · `scan` · `docx` · `image` · `legacy` (mã TCVN3/VNI)*

## Tổng hợp

Cập nhật khi thu thập xong, đối chiếu với danh sách kiểm tra ở
`docs/CHUAN-BI-DU-LIEU.md` §4.

| Chỉ tiêu | Cần | Hiện có |
|---|---|---|
| Tổng số tài liệu | ~10 | |
| PDF có lớp text | ≥ 4 | |
| PDF scan | ≥ 2 | |
| PDF mã cũ TCVN3/VNI | ≥ 1 | |
| DOCX | ≥ 1 | |
| Ảnh | ≥ 1 | |
| Có bảng biểu | ≥ 1 | |
| Có cấu trúc Chương/Điều | ≥ 4 | |
| Ngắn (< 5 trang) | ≥ 2 | |
| Dài (> 30 trang) | ≥ 1 | |
| Tiếng Anh | ≥ 1 | |

## Ba tệp cho spike M0

Việc chặn — spike S1 kiểm chứng bất biến INV-1, rủi ro số một của đồ án.
Đặt vào `spikes/samples/` với đúng tên này:

| Tên | Loại | Đã có |
|---|---|---|
| `text.pdf` | PDF có lớp text sạch | ☐ |
| `scan.pdf` | PDF scan, không có lớp text | ☐ |
| `legacy.pdf` | PDF mã cũ TCVN3/VNI *(có thì tốt, không bắt buộc)* | ☐ |
