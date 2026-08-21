# Bộ não RAG — kiểm chứng đầu-cuối

| | |
|---|---|
| Ngày | 2026-08-22 |
| Phạm vi | US-010 → US-014, US-018, US-019, US-030 → US-035, US-049, US-061, US-063, US-066 |
| Máy đã chạy | laptop (`DEVICE=cpu`, adapter giả) |
| Test | **292 xanh**, ruff sạch |

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

## Ba lỗi thật do test bắt được

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

### Bỏ dấu làm sập hai từ khác nhau về cùng một chuỗi

Luật phân loại ý định (US-066) so khớp dấu hiệu tài liệu trên văn bản **đã bỏ
dấu**, để bắt được cả câu người dùng gõ thiếu dấu. Nhưng `strip_accents` biến
cả *"mức"* lẫn *"mục"* thành `muc`, nên câu hỏi *"mức thu"* bị luật kết luận
ngay là câu tra cứu chắc chắn.

Ở đây kết luận tình cờ đúng, nhưng cơ chế thì sai — và nó sai ở **tầng rẻ nhất
và tất định nhất**, tức là chỗ khó phát hiện nhất, vì luật không bao giờ hỏi
tới mô hình để có ai đó phản bác. Cùng lỗi này với *"điều"* / *"điêu"* hay
*"chương"* / *"chuông"* sẽ định tuyến sai mà không để lại dấu vết nào.

Đã tách làm hai: nhóm từ pháp lý so khớp trên văn bản **còn dấu** (người ta hầu
như luôn gõ đủ dấu khi nhắc tới *Điều*, *Chương*, *Thông tư*), và một nhóm hẹp
hơn gồm các cụm không có từ đồng âm sau khi bỏ dấu — *quy chế*, *thông tư*,
*tài liệu* — vẫn so khớp trên bản bỏ dấu.

Cùng lượt đó, luật chào hỏi cũng lộ ra chỉ bắt được dạng cụt lủn: *"chào"* thì
khớp, *"chào bạn"* thì không, mà tiếng Việt gần như luôn có từ xưng hô hoặc
tiểu từ đi kèm.

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

## Bảng ablation đã đủ sáu dòng

| Dòng | Cờ | Test |
|---|---|---|
| **A** | chỉ vector | `test_bat_tat_nhanh_bang_cau_hinh` |
| **B** | chỉ từ khoá | `test_bat_tat_nhanh_bang_cau_hinh` |
| **C** | hybrid | `test_bat_tat_nhanh_bang_cau_hinh` |
| **D** | `RERANK_ENABLED` | `test_tat_rerank_van_chay_duoc` |
| **E** | `CONTEXTUAL_RETRIEVAL_ENABLED` | `test_tat_boi_canh_thi_khong_goi_mo_hinh` |
| **F** | `VERIFIER_ENABLED` | `test_tat_kiem_dinh_thi_khong_goi_them` |

Chứng minh US-046 AC-1: đổi cấu hình đổi hành vi mà không sửa một dòng mã nào.
Hai dòng cuối cũng khẳng định **chi phí** biến mất khi tắt — `llm.calls == []`
với dòng E, và đúng một lượt gọi mô hình với dòng F — nên phần so sánh độ trễ ở
Chương 5 có số liệu ở cả hai chiều chứ không chỉ chiều bật.

## Ba tính năng mới, ba đánh đổi phải nêu trong báo cáo

**Contextual Retrieval (US-049)** ghép 2–3 câu mô tả bối cảnh vào **cả** vector
lẫn `tsvector`. Phần mô tả nằm ở cột riêng `context_prefix`, không chạm vào
`content`, nên INV-1 nguyên vẹn và người dùng vẫn đọc đúng nguyên văn tài liệu.
Giá của nó là **một lượt gọi mô hình cho mỗi chunk** lúc nạp; `IngestResult`
mang theo `context_seconds` để con số đó vào được báo cáo. Một lượt gọi hỏng chỉ
làm chunk đó mất phần bối cảnh, không chặn cả tài liệu.

**Tác tử kiểm định (US-063)** tách vai trò *sinh* khỏi vai trò *kiểm*. Khi bộ
kiểm hỏng hoặc trả về khuôn dạng lạ thì mặc định là **ĐẠT**: một bộ kiểm không
đáng tin không được phép chặn câu trả lời vốn có thể đúng — nó là lớp bảo vệ
thêm, không phải cổng chặn. Bản sinh lại đi bằng sự kiện `replace` chứ không
phải token gửi thêm, vì giao diện không rút lại được thứ đã hiện.

**Định tuyến ý định (US-066)** cho lời chào đi thẳng, không chạy truy xuất. Khi
phân vân thì nghiêng về RAG: định tuyến nhầm một câu hỏi thật sang trò chuyện
làm mất câu trả lời có căn cứ, còn nhầm chiều ngược lại chỉ tốn vài trăm mili
giây.

## Bàn thử

`http://localhost:8000/` — trang tĩnh để nhìn thấy streaming, cổng ngưỡng, chip
trích dẫn bấm được và nút hỏi ra ngoài. Nay hiện thêm nhãn ý định, kết quả kiểm
định và bản sinh lại (viền trái màu cảnh báo), cùng nhật ký sự kiện thô — đủ để
nhìn ra ba tính năng mới có thực sự chạy hay không. **Không phải giao diện sản
phẩm**; bố cục ba cột của US-016 dựng bằng Next.js ở M2.

## Việc còn lại của bộ não

Phần logic đã đủ. Những gì còn thiếu đều **không sửa được bằng cách viết thêm
mã** — chúng cần dữ liệu thật và máy đích:

- Ngưỡng `EXTERNAL_CACHE_SIMILARITY = 0.93` **chưa hiệu chỉnh bằng dữ liệu**
  (`SPEC-REVIEW.md` §B.7). Test hiện chỉ khẳng định *"Điều 5"* và *"Điều 15"*
  phân biệt được với adapter giả.
- Ngưỡng `TAU = 0.35` cũng vậy — US-047 sẽ quét và chọn theo F1.
- Ba cờ `CONTEXTUAL_RETRIEVAL_ENABLED`, `VERIFIER_ENABLED`,
  `INTENT_ROUTING_ENABLED` đang mặc định **false**. Đó là chủ ý: bật một tính
  năng trước khi đo được nó đóng góp bao nhiêu thì bảng ablation ở Chương 5 mất
  đường cơ sở để so. M6 chạy đủ sáu dòng rồi mới chốt giá trị mặc định.
- Spike S1 và S3 vẫn chờ **tài liệu PDF tiếng Việt thật** trong `spikes/samples/`
  (bản có lớp text, bản scan, bản mã cũ TCVN3). Không có chúng thì rủi ro số một
  của đồ án — offset lệch khi tô sáng theo toạ độ — chưa được kiểm chứng trên dữ
  liệu thật.
