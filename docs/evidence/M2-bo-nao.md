# Bộ não RAG — kiểm chứng đầu-cuối

| | |
|---|---|
| Ngày | 2026-08-22 |
| Phạm vi | US-010 → US-014, US-018, US-019, US-030 → US-035, US-061 |
| Máy đã chạy | laptop (`DEVICE=cpu`, adapter giả) |
| Test | **259 xanh**, ruff sạch |

> Mọi số đo chất lượng trong tệp này **không dùng được cho báo cáo**: chúng
> chạy bằng adapter giả. Chúng chứng minh **đường ống đúng**, không chứng minh
> chất lượng. Số liệu thật đo trên máy đích ở M6.

## Luồng hoàn chỉnh, chạy thật qua API

```
POST /api/chat/ask  "thời gian đào tạo trình độ đại học là bao lâu"

session   → phiên mới, tiêu đề tự sinh từ câu hỏi
meta      → fake-echo, is_local=true
status    → retrieving → reranking → generating
token ×6  → câu trả lời hiện dần
citation  → [1] chunk 8 · trang 1 · "Chương II > Điều 4. Thời gian đào tạo"
citation  → [2] chunk 4 · trang 1 · "Chương I > Điều 1. Phạm vi điều chỉnh"
done      → grounded · 15 ms · không có marker bịa
saved     → message_id, session_id
```

Đoạn **Điều 4. Thời gian đào tạo** được trích dẫn đầu tiên — đúng đoạn trả lời
câu hỏi. Mỗi trích dẫn mang `char_start`/`char_end` cắt lại đúng nội dung, tức
là cầu nối tới tô sáng theo toạ độ (US-015) đã sẵn sàng.

## Bốn bất biến đều có test bảo vệ

| | Nội dung | Cách kiểm |
|---|---|---|
| **INV-1** | `full_text[start:end] == content` | Đột biến hai chiều ở `test_chunker`; SQL trên dữ liệu đã ghi ở `test_ingest`; qua đường trích dẫn ở `test_answer` |
| **INV-2** | Mọi text vào DB ở dạng NFC | `normalize()` của Postgres kiểm chứng độc lập |
| **INV-3** | Truy xuất tài liệu không chạm cache | Soi câu SQL đã biên dịch **và** kiểm hành vi thật: cache một chuỗi độc nhất rồi khẳng định truy xuất không trả về nó |
| **INV-4** | Lọc chủ sở hữu ở tầng SQL | Notebook của B + danh tính A → rỗng; cùng notebook + đúng chủ → có dữ liệu |

## Hai lỗi thật do test bắt được

### Thứ tự tin nhắn tuỳ tiện

`chat_messages` sắp theo `created_at`, mặc định `now()`. Trong PostgreSQL
`now()` trả về **thời điểm bắt đầu transaction**, nên câu hỏi và câu trả lời
lưu trong cùng transaction nhận **đúng một timestamp**. Phá hoà bằng `id` không
giúp gì vì đó là UUID ngẫu nhiên.

Kết quả: câu trả lời có thể hiện trước câu hỏi, và lỗi **không ổn định** — chỉ
lộ ra ở một số lần chạy tuỳ UUID sinh ra thế nào.

Đã chứng minh nguyên nhân trực tiếp trên Postgres:

```sql
BEGIN; SELECT now() = now();  -- t  (giống nhau)
```

`clock_timestamp()` sửa được phần lớn trường hợp nhưng độ phân giải chỉ là
micro giây, và với mô hình giả trả lời gần như tức thì thì hai lệnh INSERT vẫn
có thể rơi vào cùng một micro giây. Nên dùng cột `seq BIGSERIAL`: thứ tự tin
nhắn **bản chất là thứ tự chèn**, và một chuỗi tăng dần biểu diễn đúng điều đó.

Migration `0002`.

### ORM chèn NULL vào cột do máy chủ sinh

Thêm `seq` xong thì mọi lượt hỏi đáp đổ vỡ với `NotNullViolation`. SQLAlchemy
đưa `seq = NULL` vào câu INSERT vì nó coi đây là cột thường. Phải đánh dấu
`FetchedValue()` để ORM loại cột khỏi INSERT và đọc lại sau.

## Ba quyết định thiết kế đáng ghi lại

**Đường từ chối không gọi mô hình.** Đã biết tài liệu không chứa câu trả lời
thì để mô hình tự diễn đạt lời từ chối chỉ tạo cơ hội cho nó nói thêm điều nghe
hợp lý mà không có căn cứ. Câu từ chối là hằng số, và bộ đánh giá ở US-013 AC-3
đếm nó bằng so khớp chuỗi. Có test khẳng định `llm.calls == []` trên đường này.

**Chống prompt injection bằng cách ly, không bằng lọc.** Nội dung tài liệu là
dữ liệu của bên thứ ba. Mỗi đoạn được bọc delimiter, system prompt nói rõ phần
bên trong là dữ liệu chứ không phải chỉ thị, và **chuỗi delimiter bị loại khỏi
chính nội dung** để tài liệu không giả mạo được ranh giới. Có test nạp một tệp
độc hại thật và khẳng định câu tiêm vẫn nằm trong vùng dữ liệu.

**Câu hỏi đã gộp chỉ dùng để truy xuất.** Thứ lưu vào lịch sử là câu hỏi gốc.
Lưu câu đã gộp làm lịch sử đọc không giống thứ người dùng đã gõ, và lượt
condense sau sẽ gộp trên một bản đã bị viết lại — sai số cộng dồn qua từng lượt.

## Ba dòng đầu của bảng ablation đã chạy được

`test_bat_tat_nhanh_bang_cau_hinh` tham số hoá đúng cấu hình **A** (chỉ vector),
**B** (chỉ từ khoá), **C** (hybrid), và `test_tat_rerank_van_chay_duoc` phủ
dòng **D**. Chứng minh US-046 AC-1: đổi cấu hình đổi hành vi mà không sửa mã.

## Bàn thử

`http://localhost:8000/` — trang tĩnh để nhìn thấy streaming, cổng ngưỡng, chip
trích dẫn bấm được và nút hỏi ra ngoài. **Không phải giao diện sản phẩm**; bố
cục ba cột của US-016 dựng bằng Next.js ở M2.

## Việc còn lại của bộ não

- **US-049 Contextual Retrieval** — dòng E của ablation.
- **US-063 tác tử kiểm định** — dòng F.
- **US-066 định tuyến ý định** — tránh truy xuất cho câu chào hỏi.
- Ngưỡng `EXTERNAL_CACHE_SIMILARITY = 0.93` **chưa hiệu chỉnh bằng dữ liệu**
  (`SPEC-REVIEW.md` §B.7). Test hiện chỉ khẳng định *"Điều 5"* và *"Điều 15"*
  phân biệt được với adapter giả.
- Ngưỡng `TAU = 0.35` cũng vậy — US-047 sẽ quét và chọn theo F1.
