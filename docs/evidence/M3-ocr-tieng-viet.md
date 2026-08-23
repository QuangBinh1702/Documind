# M3 — Nhận dạng chữ trên tài liệu tiếng Việt

**Ngày đo:** 2026-08-23 · **Máy:** laptop phát triển, CPU (`DEVICE=cpu`)
**Liên quan:** US-023, US-024, US-048, US-056

Ghi lại số đo thật của bước OCR, và một phát hiện quan trọng đủ để đưa vào
Chương 5: **không tin được vào điểm tin cậy do engine tự báo.**

---

## 1. Tài liệu đo

| | |
|---|---|
| Tệp | Thông tư 08/2021/TT-BGDĐT — Quy chế đào tạo trình độ đại học |
| Dạng | PDF scan, **không có lớp văn bản** |
| Số trang | 22 |
| Nguồn | Cổng thông tin điện tử Bộ GD&ĐT (xem `eval/dataset/NGUON.md`) |

Trước khi có US-024, tệp này bị từ chối ngay ở cổng nạp với mã
`SCAN_NO_TEXT_LAYER`: 22/22 trang dưới ngưỡng 100 ký tự, tỉ lệ 1.00 ≥ 0.5.

---

## 2. Chọn mô hình nhận dạng — đo, không đoán

Cùng một trang, cùng một engine (RapidOCR / PP-OCRv5 mobile / ONNX Runtime),
chỉ đổi `OCR_REC_LANG`:

| `OCR_REC_LANG` | Đọc ra | Tỉ lệ dấu | Điểm chất lượng US-056 | Engine tự báo |
|---|---|---|---|---|
| `ch` (mặc định) | `Thong tu s6 10/2018 ... ngay 30 thang 3` | 0.001 | **0.45 — RỚT** | 0.98 |
| `latin` | `Thông tur só 10/2018 ... ngày 30 tháng 3` | 0.150 | **1.00 — ĐẠT** | 0.94 |

### Phát hiện: điểm tin cậy của engine không phát hiện được ca hỏng nặng nhất

Mô hình `ch` trả về **0.98** cho một kết quả đã mất sạch dấu tiếng Việt. Nó tự
tin vì nó đọc đúng những ký tự nó biết — nó chỉ không có ă, â, ê, ô, ơ, ư, đ và
các dấu thanh trong bộ ký tự đầu ra, nên nó im lặng bỏ đi.

Với văn bản pháp quy, mất dấu là mất nghĩa: *"mức thu"* và *"mục thu"* đều thành
`muc thu`. Hệ quả với hệ thống này còn nặng hơn một lỗi chính tả, vì nhánh BM25
đánh chỉ mục trên chính chuỗi đó.

**Cái bắt được ca này là cổng chất lượng US-056**, chứ không phải engine: nó đo
tỉ lệ ký tự có dấu trên văn bản trông như tiếng Việt, nên 0.001 rớt ngay. Đây là
lập luận thiết kế đáng nêu ở báo cáo — một cổng chất lượng độc lập với engine bắt
được đúng loại lỗi mà engine không tự thấy.

---

## 3. Kết quả trên toàn tài liệu

Cấu hình: `OCR_ENGINE=rapid`, `OCR_REC_LANG=latin`, `OCR_DPI=150`, CPU.

| Chỉ số | Giá trị |
|---|---|
| Trang | 22 |
| Ký tự đọc được | 40 028 |
| Thời gian | 364 s (≈ **16,5 s/trang** trên CPU) |
| Tỉ lệ dấu | 0,150 |
| Điểm chất lượng | **1,00** (ngưỡng 0,60) |
| Nhận là tiếng Việt | có |

Tài liệu đi hết đường ống và tìm kiếm được. Trích một đoạn nguyên văn:

```
18 tháng 6 nm 2012;
Cn cú Luât sira dói, bó sung mt só dièu cua Luât Giáo duc dai hąc ngày
19 tháng 11 nm 2018;
Cn cú Nghi dinh só 69/2017/ND-CP ngày 25 tháng 05 nm 2017 cúa Chính
phù quy dinh chúc nng, nhim vu, quyên han và co cáu tó chúc cúa B Giáo duc và
Dào tao;
```

### Đọc kết quả này cho đúng

Điểm 1,00 **không có nghĩa là đọc đúng**. Cổng chất lượng đo tài liệu *có trông
như tiếng Việt viết có dấu hay không*; nó không so được với bản gốc, vì không có
bản gốc để so. Văn bản trên vẫn sai một cách hệ thống:

| Đúng | Đọc ra | Ký tự thiếu |
|---|---|---|
| năm | nm | ă |
| Căn cứ | Cn cú | ă, ứ |
| sửa đổi | sira dói | ử, đ |
| đại học | dai hąc | đ |
| chức năng, nhiệm vụ | chúc nng, nhim vu | ứ, ă, ệ |

Nguyên nhân chung: bộ ký tự đầu ra của mô hình LATIN **không có ư, ơ, ă, đ**.
Chữ nào chứa chúng thì hoặc mất ký tự, hoặc bị thay bằng ký tự gần giống.

**Đây là hạn chế của công cụ sẵn có, không phải của thiết kế.** `OcrProvider` là
một cổng: khi có mô hình nhận dạng tiếng Việt, đổi `OCR_REC_LANG` là xong, không
phải sửa đường xử lý. Đó là lý do cổng này tồn tại.

---

## 4. Engine đã thử

| Engine | Trạng thái |
|---|---|
| **RapidOCR** (PP-OCRv5, ONNX Runtime) | **Đang dùng.** Vài chục MB, chạy được trên CPU |
| PaddleOCR (PP-OCRv5, PaddlePaddle) | Adapter đã viết, **không chạy được**: `paddlepaddle 3.0.0` từ chối nạp chính mô hình PaddleOCR tải về — `ValueError: (InvalidArgument) Type of attribute: strides is not right` |
| Tesseract | Chưa thử |

Adapter `paddle` được **giữ lại** dù chưa chạy: lỗi thuộc về phiên bản thư viện
chứ không thuộc về mã, và US-048 cần so nhiều engine.

---

## 5. Còn thiếu để đóng US-048

Ba trục CER · thời gian · VRAM thì mới có thời gian.

- [ ] **CER** — cần 20 trang gõ tay làm bản đối chiếu. Việc này người làm đồ án
      phải tự làm; không có bản gốc thì không tính được tỉ lệ lỗi ký tự.
- [ ] **VRAM** — phải đo trên máy đích 16 GB. Số đo trên CPU không mang nghĩa.
- [ ] **Tesseract** — thêm một adapter nữa để bảng so có ba dòng.

---

## 6. Việc này đổi được gì cho hệ thống

Trước: tài liệu scan bị từ chối, người dùng nhận một thông báo lỗi.
Sau: tài liệu scan nạp được, chunk được, trích dẫn về đúng trang và đúng vùng
toạ độ — vì `OcrProvider` trả về hộp bao chứ không chỉ trả về chữ, nên tô sáng
trích dẫn (US-015) hoạt động y hệt tài liệu có lớp văn bản.

Bất biến INV-1 được kiểm trên chính đường này
(`tests/test_ingest.py::test_ban_scan_duoc_OCR_thi_nap_binh_thuong`).
