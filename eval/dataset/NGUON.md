# Xuất xứ tài liệu kiểm thử

Bảng này vào phụ lục báo cáo và trả lời câu hỏi về nguồn gốc dữ liệu khi bảo vệ
(US-044 AC-7).

Tệp gốc **không commit** — `*.pdf` nằm trong `.gitignore`. Thứ được lưu là
`nguon.csv` (URL để tải lại đúng bộ) và bảng đo dưới đây.

## Nguyên tắc chọn

Chỉ dùng **văn bản công khai**: pháp quy, quy chế, thông tư, quyết định do các
cơ quan nhà nước và trường đại học tự công bố. Không đưa giáo trình có bản
quyền vào bộ kiểm thử — xem `docs/CHUAN-BI-DU-LIEU.md` §3.

## Tải lại bộ dữ liệu

```powershell
python eval/tai_tai_lieu.py     # đọc nguon.csv, tải vào documents/
python eval/corpus_report.py    # đối chiếu với chỉ tiêu bên dưới
```

## Danh mục — đo ngày 2026-08-21

Cột **Loại** là thứ hệ thống **đọc được**, không phải thứ tên tệp hứa hẹn. Nó do
`eval/corpus_report.py` sinh ra bằng chính đường trích xuất của sản phẩm, nên
nếu bộ trích xuất đọc sai một tệp thì bảng này lộ ra ngay.

| # | Tệp | Nhóm | Loại | Trang | Ký tự | Chất lượng | Tiêu đề | Chương/Điều | Dòng bảng |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `qc-dao-tao-hust-2023.pdf` | quy-che | text | 32 | 76,449 | 1.00 | 106 | có | 0 |
| 2 | `qc-dao-tao-tantrao-cd.pdf` | quy-che | text | 28 | 53,734 | 1.00 | 36 | có | 1 |
| 3 | `qc-dao-tao-tbd-2024.pdf` | quy-che | text | 26 | 50,627 | 1.00 | 63 | có | 0 |
| 4 | `qc-dao-tao-uit-2022.pdf` | quy-che | text | 27 | 64,504 | 1.00 | 80 | có | 0 |
| 5 | `qd-ngoai-ngu-hust-2024.pdf` | quy-che | text | 3 | 4,458 | 1.00 | 3 | có | 2 |
| 6 | `qd-243-dao-tao-tu-xa-hue.pdf` | quyet-dinh | text | 22 | 57,321 | 1.00 | 33 | có | 1 |
| 7 | `qd-998-dao-tao-tu-xa-hcmulaw.pdf` | quyet-dinh | **scan** | 43 | 43 | 0.58 | 0 | — | 0 |
| 8 | `tt08-2021-quy-che-dao-tao-dh.pdf` | thong-tu | **scan** | 22 | 22 | 0.58 | 0 | — | 0 |

Tổng phần đọc được: **307 093 ký tự**, 138 trang có lớp text, 321 tiêu đề.

## Ba điều bảng này làm lộ ra

**Thông tư 08/2021 là bản scan.** Đây là văn bản gốc mà sáu quy chế trường trong
bộ đều dẫn xuất từ đó, và bản phổ biến trên mạng là ảnh chụp có đóng dấu chứ
không có lớp text. Đã thử sáu nguồn khác nhau, không nguồn nào có bản text.

Không phải trở ngại: sáu quy chế trường có cùng cấu trúc *Chương / Điều* và
phần lớn nội dung là diễn giải lại chính Thông tư đó, nên nội dung cần hỏi vẫn
nằm trong bộ. Ngược lại, hai bản scan là **ca kiểm thử thật cho đường OCR**
(US-024) — thứ trước đây chỉ có PDF tự sinh để thử.

**Một tệp tải về bị đứt giữa chừng và trông vẫn như PDF hợp lệ.**
`qd-998` lần đầu tải về 19,8 MB, header `%PDF-1.7` đúng, nhưng `page_count = 0`.
Cổng trích xuất bắt được bằng `PDF_EMPTY`. Tải lại đủ thì ra 43 trang. Đây là lý
do `corpus_report.py` mở từng tệp ra đo thay vì tin vào kích thước tệp.

**Không có tài liệu nào nhiều bảng biểu.** Văn bản pháp quy tiếng Việt chủ yếu
là văn xuôi đánh số. Muốn phủ ca bảng biểu thì phải chủ động tìm phụ lục hoặc
khung chương trình đào tạo.

## Đối chiếu chỉ tiêu

| Chỉ tiêu | Cần | Hiện có | |
|---|---|---|---|
| Tổng số tài liệu | 10 | 8 | thiếu 2 |
| PDF có lớp text | 4 | 6 | ✓ |
| PDF scan | 2 | 2 | ✓ |
| PDF mã cũ TCVN3/VNI | 1 | 0 | thiếu 1 |
| DOCX | 1 | 0 | thiếu 1 |
| Có bảng biểu | 1 | 0 | thiếu 1 |
| Có cấu trúc Chương/Điều | 4 | 6 | ✓ |
| Ngắn (< 5 trang) | 2 | 1 | thiếu 1 |
| Dài (> 30 trang) | 1 | 2 | ✓ |

Bốn chỉ tiêu còn thiếu đều thuộc phần **kiểm thử độ bền của bước trích xuất**
(US-007, US-056), không thuộc phần đo chất lượng truy xuất và trả lời. Bộ hiện
có đã đủ để chạy US-044 → US-047; bốn chỉ tiêu kia bổ sung sau mà không phải
làm lại gì.

Ghi chú cho từng chỉ tiêu còn thiếu:

- **DOCX** — các trường công bố quy chế dưới dạng PDF; bản `.docx` thường nằm ở
  trang biểu mẫu và phải lấy thủ công.
- **Mã cũ TCVN3/VNI** — cần văn bản số hoá từ trước khoảng 2005. Khó tìm bản
  công khai. Đường xử lý đã có test bằng chuỗi dựng tay.
- **Bảng biểu** — tìm phụ lục khung chương trình đào tạo.
- **Ngắn dưới 5 trang** — một quyết định đơn lẻ là đủ.
