# Spike M0 — ba câu hỏi rủi ro, đã chạy trên tài liệu thật

| | |
|---|---|
| Ngày | 2026-08-21 |
| Phạm vi | Spike S1, S2, S3 (`SPEC.md` §J.1, mốc M0) |
| Máy đã chạy | laptop (`DEVICE=cpu`); S2 cần server 16 GB |
| Tệp mẫu | 3 PDF thật trong `spikes/samples/` |

## Tệp mẫu

| Tệp | Trang | Ký tự lớp text | Vai trò |
|---|---|---|---|
| `dashboard-…7d.pdf` | 1 | 304 | Tệp ngắn, gần như không có nội dung |
| `LabATTT Danh sach de tai…pdf` | 85 | 213 705 | Ca thường — tài liệu tiếng Việt dài, có cấu trúc |
| `live-sessions-20260723.pdf` | 2 | 0 | Bản scan, không có lớp văn bản |

Chưa có tệp mã cũ TCVN3/VNI. Ca hỏng nguy hiểm nhất (`SPEC-REVIEW.md` §B.2) vẫn
chỉ được kiểm bằng chuỗi dựng tay trong test.

## S1 — bất biến offset: **ĐẠT**

```
LabATTT Danh sach de tai bao cao mon hoc (CURRENT).pdf
  trang: 85  ký tự: 213705  chunk: 315
  INV-1 offset khớp: 315/315
  INV-2 toàn chuỗi là NFC: CÓ
  tỉ lệ ký tự thay thế (U+FFFD): 0.00000
```

Đường ống sản phẩm cho kết quả bằng đường spike: **119/119 đoạn**, kiểm bằng
`verify_offsets` trên dữ liệu **đã ghi vào Postgres**. Chi tiết và lý do giữ
nguyên thiết kế: `docs/decisions/0002-bat-bien-offset-tren-pdf-that.md`.

Rủi ro số một của đồ án (`SPEC.md` §J.6) đã đóng.

## S3 — tô sáng theo toạ độ: **dữ liệu đã có, chờ mắt người xác nhận**

Tìm cụm *"báo cáo"* trong tài liệu 85 trang: **29 kết quả**, không trang nào có
`/Rotate`, không trang nào có `CropBox` khác `MediaBox` — tức là phép quy đổi
`css = pdf_point × scale` áp dụng được nguyên vẹn, không phải bù trừ gì.

```
trang 3: (289.74, 119.36) → (329.99, 132.64) trên khổ 841.75×595.5
```

Trang khổ ngang A4. Kết quả nằm ở `spikes/out/s3_highlight.html`.

**Việc còn lại là của người, không của máy:** mở tệp HTML đó bằng trình duyệt và
nhìn xem ô vàng có phủ đúng cụm từ ở mọi mức zoom không. Không có cách nào kiểm
điều đó bằng test tự động, vì câu hỏi thật sự là *hệ toạ độ của PDF.js có khớp
hệ toạ độ của PyMuPDF không* — chỉ trình duyệt trả lời được.

| Nhìn thấy gì | Kết luận |
|---|---|
| Đúng ở mọi zoom | Bậc 1 khả thi, US-015 làm được như thiết kế |
| Lệch cố định | Sai gốc toạ độ |
| Lệch tăng theo zoom | Sai hệ số scale |

## S2 — ngân sách VRAM: **chưa chạy**

Cần máy đích 16 GB. Câu hỏi 2 GB VRAM của laptop đã được trả lời từ trước và
dẫn tới mô hình hai máy ở `SPEC-v1.md` §10.0.

## Hai lỗi thật do tệp mẫu làm lộ ra

### US-023 chưa được cài đặt

Bản scan bị chặn đúng nhưng với chẩn đoán sai: *"chỉ 0% ký tự là chữ cái, có thể
là bảng biểu, mục lục"*. Cột `sources.is_scanned` và hai tham số cấu hình đã có
sẵn, nhưng không dòng mã nào đọc chúng — cổng chất lượng US-056 vô tình che mất
khoảng trống đó, vì mọi bản scan đều rớt nên không ai nhận ra chúng rớt vì nhầm
lý do. Đã cài, đã tách thành cổng riêng:
`docs/decisions/0003-phat-hien-ban-scan-tach-khoi-cong-chat-luong.md`.

### Spike S3 soi nhầm tệp

`find_pdf()` chọn tệp đầu bảng chữ cái. Với tệp thật — tên không bao giờ là
`text.pdf` — nó vớ phải bản xuất dashboard 304 ký tự và báo *"không tìm thấy"*,
trông hệt như người dùng gõ sai cụm từ. Nay chọn theo **lớp text dày nhất**, và
in ra số ký tự của từng tệp để thấy được nó đang soi tệp nào.

Cùng lượt đó: trang HTML trỏ tới tệp PDF bên cạnh, mà Chrome chặn vì chính sách
CORS của giao thức `file://`, và tên tệp thật có dấu cách với dấu ngoặc làm hỏng
URL. Nay PDF được nhúng thẳng vào trang dưới dạng base64.

## Một mối lo cũ đã đóng

Quyết định 0001 để treo câu hỏi liệu `ts_rank_cd` có hoà điểm nhiều không —
trên bộ test tí hon nó trả về `0.1` cho mọi tài liệu. Đo lại trên 118 đoạn thật:
101 đoạn khớp truy vấn, **87 mức điểm khác nhau**, và mười hai đoạn đầu bảng
không đoạn nào hoà. Vì RRF chỉ dùng thứ hạng và chỉ vùng đầu bảng mới ảnh hưởng
kết quả, đây đúng là chỗ cần phân biệt được. Giữ `ts_rank_cd`.

## Đường ống chạy thật trên tài liệu 85 trang

```
python -m app.cli.search "sinh vien nop bao cao mon hoc khi nao"

[1] RRF 0.03279 · trang 13 · hạng: fulltext=#1  vector=#1
     Mục 2.17 / 2.18: Phát hiện tấn công mạng dựa trên Machine Learning
[2] RRF 0.02903 · trang 14 · hạng: fulltext=#16 vector=#3
[3] RRF 0.02886 · trang 12 · hạng: fulltext=#3  vector=#17
```

`heading_path` bắt đúng cấu trúc mục của tệp, `page_no` khớp trang thật, cả hai
nhánh đều góp ứng viên và RRF hợp nhất được thứ hạng lệch nhau giữa hai nhánh.

> Vector ở đây sinh bằng adapter giả, nên **thứ tự kết quả không nói lên chất
> lượng truy xuất**. Nó chứng minh đường ống chạy đúng trên dữ liệu thật, không
> chứng minh chất lượng. Số liệu thật đo ở M6 trên máy đích.
