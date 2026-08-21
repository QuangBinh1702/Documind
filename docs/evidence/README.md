# Bằng chứng hoàn thành story

Mỗi story hoàn thành để lại **một tệp** ở đây: `US-0xx.md`. Đây là yêu cầu
§A.6 của `SPEC.md`.

Thư mục này phục vụ ba việc cùng lúc:

1. **Tự kiểm tra khi làm** — buộc phải chạy thật từng AC thay vì tick theo trí nhớ.
2. **Kho hình cho Chương 4** — ảnh chụp màn hình lấy trực tiếp từ đây (US-054b AC-3).
3. **Bằng chứng khi bảo vệ** — trả lời được câu *"có gì chứng minh?"*.

Vì làm một mình, không có ai xác nhận hộ. Tệp bằng chứng là thứ thay thế.

## Mẫu

Sao chép `_TEMPLATE.md` khi bắt đầu một story mới.

## Quy ước

- Đặt tên đúng mã story: `US-014.md`, không phải `citation.md`.
- Ảnh đặt cùng thư mục, tên bắt đầu bằng mã story: `us-014-chip.png`.
- Video (`.mp4`, `.mov`) **không được commit** — `.gitignore` đã chặn. Giữ cục bộ,
  chỉ commit ảnh trích từ video nếu cần.
- Ghi **số đo thật**, kể cả khi chưa đạt. Một AC không đạt kèm số thật và lý do
  có giá trị hơn một dấu tick không có gì đứng sau.
- AC có mốc thời gian chỉ ghi được là ĐẠT khi đo **trên máy đích** (server 16 GB).
  Số đo trên laptop `DEVICE=cpu` phải ghi rõ là để gỡ lỗi, không phải nghiệm thu.
