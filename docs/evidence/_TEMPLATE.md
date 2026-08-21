# US-0xx · Tiêu đề story

| | |
|---|---|
| Ngày hoàn thành | YYYY-MM-DD |
| Commit | `xxxxxxx` |
| Máy đã chạy | laptop (`DEVICE=cpu`) / server (16 GB VRAM) |

## Kết quả từng AC

| AC | Kết quả | Bằng chứng |
|---|---|---|
| 1 | ✅ Đạt | |
| 2 | ✅ Đạt | |
| 3 | ⚠ Một phần | xem ghi chú |
| 4 | ❌ Chưa đạt | số đo thật + lý do |

## Số đo

*Chỉ ghi những AC có ngưỡng số. Ghi con số thật, không ghi "đạt".*

| Chỉ số | Yêu cầu | Đo được | Máy |
|---|---|---|---|
| | | | |

## Test

```
$ pytest tests/... -q
```

*Dán kết quả thật. Cả bộ test cũ cũng phải xanh (DoD D6).*

## Checklist DoD (`SPEC.md` §A.4)

- [ ] D1 mọi AC pass thủ công
- [ ] D2 AC có ngưỡng đã đo, ghi số thật
- [ ] D3 đã thử đường lỗi, không chỉ đường thành công
- [ ] D4 tách lớp router → service → repository
- [ ] D5 story lõi có unit test, test xanh
- [ ] D6 toàn bộ test cũ vẫn xanh
- [ ] D7 không hardcode tham số, đã thêm vào `.env.example`
- [ ] D8 không còn TODO chặn, code chết, `print()` gỡ lỗi, secret
- [ ] D9 text vào DB đã chuẩn hoá NFC; test offset vẫn xanh
- [ ] D10 chuỗi hiển thị có đủ VI và EN
- [ ] D11 lỗi hiện thông báo tiếng Việt, traceback chỉ trong log
- [ ] D12 endpoint mới kiểm tra quyền sở hữu, truy cập chéo trả 404
- [ ] D13 đã commit kèm mã story; có migration nếu đổi schema
- [ ] D14 sơ đồ cập nhật; quyết định kỹ thuật đã ghi vào `docs/decisions/`

## Checklist bổ sung theo loại (`SPEC.md` §A.5)

*Xoá các loại không áp dụng.*

**Loại 1 — pipeline dữ liệu:** 4 loại đầu vào · ít nhất 1 tệp tiếng Việt thật ·
không kẹt trạng thái trung gian · xử lý lại cho kết quả giống nhau.

**Loại 2 — retrieval / sinh:** unit test cho thuật toán thuần · tham số đổi được
qua config · đã thử câu hỏi tiếng Việt có dấu và câu chứa mã hiệu · log truy vết đủ.

**Loại 3 — giao diện:** 1920/1366/<1024 · ba trạng thái rỗng-tải-lỗi · dùng được
bằng bàn phím · đã chụp màn hình.

**Loại 4 — đánh giá:** chạy bằng một lệnh · kết quả ra tệp trong repo · tái lập
được (seed + revision model) · có biểu đồ · ghi cả kết quả xấu.

**Loại 5 — tài liệu:** người khác làm theo được · đã tự làm lại từ đầu để kiểm chứng.

## Ghi chú cho báo cáo

- **Hình cho Chương x:** `us-0xx-....png`
- **Quyết định:** *chọn gì · vì sao · đã cân nhắc phương án nào · đánh đổi gì*

## Việc còn lại

*Nếu có AC chưa đạt: nêu rõ chặn ở đâu và story nào sẽ xử lý.*
