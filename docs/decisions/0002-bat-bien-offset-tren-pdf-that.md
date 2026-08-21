# 0002 Giữ nguyên thiết kế offset sau khi kiểm chứng trên PDF thật

Date: 2026-08-21

## Status

Accepted

## Context

`SPEC.md` §J.6 xếp **offset lệch** là rủi ro số một của đồ án. Toàn bộ tính năng
trích dẫn — thứ phân biệt DocuMind với một chatbot thường — dựng trên bất biến
INV-1:

```
source_texts.full_text[chunk.char_start:chunk.char_end] == chunk.content
```

Nếu bất biến này sai, chip trích dẫn trỏ sai chỗ, tô sáng theo toạ độ (US-015)
không dựng được, và không có cách nào sửa ngoài việc thiết kế lại tầng lưu văn
bản. Spike S1 tồn tại để trả lời câu hỏi đó **trước khi** viết mã sản phẩm.

Cho tới hôm nay S1 vẫn treo vì thiếu PDF tiếng Việt thật. Bộ test dùng PDF do
PyMuPDF tự sinh, mà PDF tự sinh không có những thứ làm hỏng offset trong thực
tế: thứ tự khối lộn xộn, ligature, ký tự tổ hợp NFD, trang xoay, cột đôi.

Ba tệp thật đã được đưa vào `spikes/samples/`: một bản xuất dashboard một trang,
một danh sách đề tài môn học 85 trang, và một bản scan hai trang.

## Decision

**Giữ nguyên thiết kế hiện tại.** Không đổi `source_texts`, không đổi thứ tự
chuẩn hoá, không đổi cách `TextBuilder` dựng offset.

Đã kiểm chứng hai lần, bằng hai đường mã độc lập:

| Đường | Kết quả |
|---|---|
| Spike S1 (mã tối giản, chunk 800 ký tự cố định) | **316/316** chunk cắt lại đúng, mọi tệp đều NFC |
| Đường ống sản phẩm (`app.cli.ingest`, chunk theo token, tôn trọng tiêu đề) | **119/119** chunk, `verify_offsets` kiểm trên dữ liệu **đã ghi vào Postgres** |

Tài liệu 85 trang cho 118 đoạn, `heading_path` bắt đúng cấu trúc *Mục 2.17 /
2.18* của tệp, `page_no` khớp trang thật. Không có ký tự U+FFFD nào, không có
lệch độ dài giữa ghép-rồi-chuẩn-hoá và chuẩn-hoá-rồi-ghép.

## Alternatives Considered

1. **Lưu `content` riêng và coi offset là dữ liệu tham khảo.**
   Đơn giản hơn, nhưng khi hai bản lệch nhau thì không có gì phát hiện được, và
   trích dẫn sai vẫn hiển thị như trích dẫn đúng. Bất biến chỉ có giá trị khi
   nó được kiểm.

2. **Tìm lại vị trí bằng `full_text.find(content)` lúc cần.**
   Hỏng ngay khi một đoạn xuất hiện hai lần trong tài liệu — chuyện rất thường
   gặp với văn bản pháp quy có điều khoản lặp. Đây chính là lý do `TextBuilder`
   **dựng** offset lúc nối chứ không **đi tìm**.

3. **Chuẩn hoá NFC từng trang rồi mới ghép.**
   Spike S1 có sẵn phép kiểm cho khả năng này vì tổ hợp Unicode có thể xảy ra
   vắt qua ranh giới trang. Trên dữ liệu thật không xảy ra lệch, nhưng thiết kế
   hiện tại đã phòng sẵn bằng cách ngăn cách các mảnh bằng `\n` — ký tự này
   chặn mọi tổ hợp vắt ranh giới, nên `normalize(a) + "\n" + normalize(b)` luôn
   bằng `normalize(a + "\n" + b)`.

## Consequences

Positive:

- **Rủi ro số một của đồ án đã đóng.** US-015 làm được như thiết kế; không cần
  tụt xuống bậc giảm cấp nào vì lý do offset.
- Đường ống sản phẩm cho kết quả bằng đường spike, nên phần phức tạp thêm của
  nó — chunk theo token, tôn trọng tiêu đề, chồng lặp — không làm hỏng bất biến.
- `verify_offsets` chạy trên dữ liệu **đã ghi vào cơ sở dữ liệu**, nên nó bắt
  được cả lỗi phát sinh ở tầng lưu trữ chứ không chỉ lỗi trong bộ nhớ.

Tradeoffs:

- Ba tệp mẫu **không có bản mã cũ TCVN3/VNI**. Đường xử lý đó vẫn chỉ được kiểm
  bằng chuỗi dựng tay trong test. Đây là ca hỏng nguy hiểm nhất (`SPEC-REVIEW.md`
  §B.2) và vẫn chưa có bằng chứng trên tệp thật.
- Tài liệu mẫu là danh sách đề tài môn học, không phải văn bản pháp quy nhiều
  tầng *Phần / Chương / Mục / Điều*. Bộ nhận diện tiêu đề đã chạy đúng trên cấu
  trúc *Mục x.y*, nhưng cấu trúc pháp quy đầy đủ chưa được kiểm trên tệp thật.

## Follow-Up

- Tìm một PDF pháp quy tiếng Việt thật cho bộ đánh giá ở M6 (`eval/dataset/`).
- Nếu tìm được tệp TCVN3 thật, chạy lại S1 để kiểm chứng cổng chất lượng US-056
  trên dữ liệu thật thay vì chuỗi dựng tay.
- **Xoá `spikes/` sau khi cả ba quyết định đã ghi xong** — mã spike không mang
  vào sản phẩm (`spikes/README.md`).
