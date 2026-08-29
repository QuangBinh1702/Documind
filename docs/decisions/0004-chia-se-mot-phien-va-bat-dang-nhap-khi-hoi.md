# 0004 Chia sẻ một phiên hội thoại, và bắt đăng nhập khi hỏi

Date: 2026-08-29

## Status

Accepted — thay thế một phần US-039 AC-2 và AC-4.

## Context

US-039 mô tả chia sẻ ở mức **notebook**: liên kết mở ra danh sách nguồn, người
xem hỏi được mà không cần tài khoản, và mọi chi phí tính cho chủ sở hữu.

Bản cài đặt theo đúng mô tả đó, và nó hỏng trong tay người dùng thật. Người
dùng chia sẻ ngay sau khi vừa hỏi xong một câu họ thấy hay, rồi mở liên kết ra
kiểm tra và thấy một màn hình trống: đúng danh sách nguồn, đúng ô nhập, không
có đoạn hỏi đáp nào. Không có gì trên giao diện giải thích được điều đó, vì
theo thiết kế thì không có gì sai cả — hội thoại chưa bao giờ nằm trong phạm vi
chia sẻ.

Nhìn lại thì AC-2 mô tả đúng thứ *hệ thống làm được* chứ không phải thứ *người
dùng muốn gửi đi*. Cái người ta muốn gửi là **một đoạn hỏi đáp cụ thể**, còn
tài liệu chỉ đi kèm để kiểm chứng trích dẫn.

Đồng thời, hai điều khoản của AC-4 tự mâu thuẫn khi gặp thực tế: người xem
không có tài khoản nên chi phí phải tính cho chủ sở hữu, nhưng khi ấy phát một
liên kết ra đồng nghĩa với phát hạn mức của mình cho bất kỳ ai chuyển tiếp được
đường link — và câu hỏi của người xem không có chỗ nào để lưu, nên họ đóng tab
là mất.

## Decision

**Liên kết chia sẻ trỏ tới một phiên hội thoại. Đọc thì không cần tài khoản,
hỏi thì cần.**

Ba phần cụ thể:

1. **`share_links.session_id`** — liên kết mang theo phiên được chia sẻ. Người
   nhận mở ra thấy trọn đoạn hỏi đáp kèm chip trích dẫn bấm được. Bỏ trống
   `session_id` là hình thái cũ, chia sẻ notebook mà không kèm hội thoại nào;
   giữ lại để những liên kết đã phát đi trước migration 0004 vẫn sống.

2. **`chat_sessions.user_id`** — phiên có chủ sở hữu riêng, không suy ra từ
   notebook nữa. Đây là phần bắt buộc phải đi kèm: thiếu nó thì không có cách
   nào diễn đạt "hai người cùng hỏi trong một notebook" ở tầng SQL.

3. **`POST /api/shared/{token}/ask` đòi đăng nhập.** Phiên sinh ra thuộc về
   người hỏi và hiện trong lịch sử của họ (`/api/shared/{token}/my-sessions`),
   không lẫn vào lịch sử của chủ notebook.

Người xem cũng đọc được **toàn văn** tài liệu qua
`/api/shared/{token}/sources/{id}/file` và `/text`. Không có nó thì trích dẫn
không kiểm chứng được: một đoạn văn tách khỏi ngữ cảnh quanh nó chứng minh được
rất ít, và US-015 vốn đòi mở đúng trang rồi tô sáng đúng chỗ.

## Alternatives Considered

1. **Chia sẻ toàn bộ lịch sử của notebook.**
   Không cần cột `session_id`, và người nhận chọn phiên để đọc. Bị loại vì nó
   thay đổi ý nghĩa của **những liên kết đã phát đi**: một token cấp cho ai đó
   hôm qua để xem tài liệu sẽ đột nhiên mở ra mọi hội thoại kể từ đó. Mở rộng
   quyền của một thứ đã nằm trong tay người khác thì không thu lại được.

2. **Giữ nguyên cho hỏi ẩn danh, chỉ thêm phần đọc hội thoại.**
   Ít việc hơn hẳn và không cần đụng tới `chat_sessions`. Bị loại vì nó để
   nguyên hai vấn đề của AC-4: hạn mức của chủ sở hữu vẫn bị người lạ tiêu, và
   câu hỏi của người xem vẫn không có chỗ lưu. Bắt đăng nhập giải quyết cả hai
   bằng một thay đổi, và đó cũng là điều người dùng chọn khi được hỏi.

3. **Bỏ hẳn ô nhập, liên kết thành chỉ đọc thuần tuý.**
   Rẻ nhất và an toàn nhất về hạn mức. Bị loại vì hỏi đáp được chính là thứ
   phân biệt một liên kết DocuMind với việc gửi kèm một tệp PDF — nguyên văn
   AC-2, và là phần đáng demo nhất của tính năng.

## Consequences

Positive:

- Chia sẻ làm đúng thứ người dùng tưởng nó làm. Đây là một lỗi **không có
  triệu chứng ở phía người gửi**: họ thấy hội thoại của mình bình thường, chỉ
  người nhận mới thấy trống.
- Chi phí tính đúng người. Phát liên kết không còn là phát hạn mức của mình.
- Người xem xem lại được hội thoại của chính mình, kể cả trong notebook không
  thuộc về họ.
- `chat_sessions.user_id` khiến INV-4 kiểm được thẳng ở tầng SQL cho hội thoại,
  thay vì đi vòng qua một phép nối mà đúng-vì-tình-cờ.

Tradeoffs:

- **Rào cản đăng nhập.** Người nhận muốn hỏi thì phải lập tài khoản. Với một
  đồ án hướng tới nhóm sinh viên cùng lớp thì chấp nhận được, nhưng nó làm
  chậm khoảnh khắc demo so với bản ẩn danh.
- **Người cầm liên kết đọc được toàn văn tài liệu**, không chỉ đoạn được trích.
  Trên thực tế phạm vi không rộng thêm — người xem vốn đã hỏi được câu bất kỳ
  và nhận về nguyên văn các đoạn khớp — nhưng nó phải được nói rõ ở hộp chia
  sẻ, chứ không để người dùng tự phát hiện.
- **Lui migration làm mất dữ liệu.** `downgrade()` xoá những phiên không thuộc
  chủ notebook, vì lược đồ cũ không có chỗ diễn đạt chúng và phương án còn lại
  là âm thầm đổi chủ chúng sang chủ notebook.
- SPEC.md §US-039 AC-2 và AC-4 nay lệch với hệ thống. Bản thân SPEC không sửa
  được (nó là đầu bài đã nộp), nên chỗ lệch được ghi ở đây và phải trình bày
  trong báo cáo tại US-054 AC-2.

## Follow-Up

- Nêu chỗ lệch với AC-4 trong báo cáo, cùng lý do — cùng chỗ với thang giảm cấp
  của US-015.
- Cân nhắc hạn mức riêng cho câu hỏi đặt qua liên kết chia sẻ: hiện chúng dùng
  chung trần với câu hỏi thường của người hỏi.
