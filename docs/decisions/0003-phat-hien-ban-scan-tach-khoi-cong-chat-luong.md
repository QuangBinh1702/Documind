# 0003 Phát hiện bản scan là một cổng riêng, không gộp vào cổng chất lượng

Date: 2026-08-21

## Status

Accepted

## Context

Một trong ba tệp mẫu thật là PDF scan hai trang, không có lớp văn bản nào. Cho
nó đi qua đường ống sản phẩm thì nó **bị chặn đúng**, nhưng với lý do sai:

```
LỖI LOW_TEXT_QUALITY: Chất lượng văn bản 0.58 dưới ngưỡng 0.60.
Chỉ 0% ký tự là chữ cái — có thể là bảng biểu, mục lục, hoặc trang gần như rỗng
```

Tệp này không phải bảng biểu, cũng không phải mục lục. Nó là bản scan, và thứ
người dùng cần biết là *"cần OCR"* chứ không phải một con số 0.58.

Điều tra ra một khoảng trống lớn hơn: **US-023 chưa được cài đặt.** Cột
`sources.is_scanned` có trong lược đồ, hai tham số
`SCAN_CHARS_PER_PAGE_THRESHOLD` và `SCAN_PAGE_RATIO_THRESHOLD` có trong cấu
hình và trong `.env.example`, nhưng không có một dòng mã nào đọc chúng. Cổng
chất lượng US-056 vô tình che mất khoảng trống đó: mọi bản scan đều rớt, nên
không ai nhận ra là chúng rớt vì nhầm lý do.

## Decision

**Phát hiện bản scan là một cổng riêng, chạy TRƯỚC cổng chất lượng, và chỉ áp
dụng cho PDF.**

- `ExtractResult` mang thêm `page_char_counts` — số ký tự thật trên từng trang,
  **không tính ký tự ngăn cách**. `TextBuilder` chèn một `\n` cho trang rỗng để
  bản đồ trang liên tục; đếm cả ký tự đó thì mọi trang đều khác rỗng và tín
  hiệu rõ nhất bị mất.
- `looks_scanned()` xét theo **tỉ lệ trang** thiếu text, không theo tổng số ký
  tự. Ngưỡng do tầng gọi truyền vào; module trích xuất không đọc cấu hình.
- Khi là bản scan: `status = failed`, `error_code = SCAN_NO_TEXT_LAYER`, thông
  báo nêu rõ cần OCR. `is_scanned` được ghi lại **kể cả khi tệp không phải bản
  scan**, vì đó là dữ liệu đầu vào cho US-024.

## Alternatives Considered

1. **Chỉ sửa thông báo của cổng chất lượng.**
   Rẻ nhất và sai nhất. Mã lỗi là thứ định tuyến sang đường OCR ở US-024; gộp
   bản scan chung mã với văn bản chất lượng kém thì không phân biệt được ca nào
   nên gọi OCR và ca nào nên trả lại cho người dùng.

2. **Xét theo tổng số ký tự của cả tài liệu.**
   Sai ở cả hai chiều. Một bản scan 200 trang kèm vài trang bìa có text sẽ vượt
   ngưỡng và trượt qua; một tài liệu có text đúng nhưng ngắn sẽ bị chặn oan.
   Tỉ lệ trang mô tả đúng thứ đang được hỏi: *phần lớn tài liệu này có đọc được
   không?*

3. **Dùng `count_chars_per_page()` sẵn có trong `pdf.py`.**
   Hàm đó mở lại tệp lần thứ hai. Rẻ khi cần quyết định trước lúc trích xuất
   đầy đủ, nhưng ở đây tài liệu đã trích xuất xong rồi, nên đếm lại là công
   thừa. Giữ hàm đó cho đường US-024 — nơi câu hỏi được đặt ra *trước* khi bỏ
   công xử lý.

4. **Áp dụng cho mọi định dạng.**
   DOCX và TXT không có khái niệm trang; `TextBuilder` gom chúng thành đúng một
   "trang". Áp cùng luật thì mọi tệp văn bản ngắn đều thành "bản scan" — một
   kết luận vô nghĩa với định dạng vốn không thể là ảnh.

## Consequences

Positive:

- Chẩn đoán đúng tên gọi: *"Tệp là bản scan: 2/2 trang không có lớp văn bản.
  Cần nhận dạng ký tự (OCR) mới đọc được nội dung."*
- US-024 có sẵn điểm móc: một mã lỗi ổn định và một cột `is_scanned` được ghi
  cho mọi PDF, kể cả PDF bình thường.
- Tài liệu hỗn hợp — có text xen vài trang ảnh — vẫn đi đường thường, không bị
  đẩy qua OCR làm hỏng phần text vốn đã sạch.

Tradeoffs:

- Hai ngưỡng `100` ký tự/trang và tỉ lệ `0.5` là **giá trị mặc định chưa hiệu
  chỉnh**, thừa hưởng từ `SPEC.md` US-023. Chưa có dữ liệu để nói chúng đúng.
- PDF có lớp text rác từ một lần OCR kém trước đó sẽ **không** bị bắt ở cổng
  này — nó có đủ ký tự. Đó đúng là việc của cổng chất lượng US-056, và hai cổng
  bổ sung cho nhau chứ không thay thế nhau.

## Follow-Up

- US-024 (OCR) đọc `is_scanned` và `SCAN_NO_TEXT_LAYER` để định tuyến.
- Hiệu chỉnh hai ngưỡng khi bộ tài liệu đánh giá ở M6 có đủ bản scan thật.
