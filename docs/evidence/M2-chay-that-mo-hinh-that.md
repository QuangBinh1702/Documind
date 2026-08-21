# Lần đầu chạy bằng mô hình thật

| | |
|---|---|
| Ngày | 2026-08-21 |
| Nhúng | `BAAI/bge-m3` trên CPU |
| Xếp hạng lại | `BAAI/bge-reranker-v2-m3` trên CPU, 15 ứng viên |
| Sinh | `gemini-3.5-flash` (Fast Mode) |
| Tài liệu | 1 PDF thật, 85 trang, 149 đoạn |
| Test | **338 xanh**, ruff sạch |

> Đây là lần đầu cả ba adapter thật chạy cùng lúc. Trước đó mọi thứ đo bằng
> adapter giả, vốn chỉ chứng minh đường ống đúng chứ không chứng minh chất
> lượng. Số liệu độ trễ ở đây là **của CPU laptop**, không dùng cho báo cáo —
> máy đích 16 GB VRAM sẽ cho con số khác hẳn.

## Câu trả lời thật trông như thế nào

```
HỎI: Có đề tài nào về mã độc không?

Dựa trên các đoạn tài liệu được cung cấp, có các đề tài liên quan đến mã độc:

1. **Đề tài 2.10: Công cụ phân tích mã độc TUI** [1][2][7].
2. **Đề tài 2.11: Ứng dụng học máy trong phân tích mã độc Android** [3][7][8].
3. **Đề tài 2.12: Ứng dụng học máy trong nhận diện các tiến trình mã độc
   đang hoạt động trong máy** [4][5][6][7].

grounded · điểm 0.8484 · 55.8 s
  [5] trang 36  2.12 Ứng dụng học máy trong nhận diện các tiến trình mã độc…
  [8] trang 30  2.11 Ứng dụng học máy trong phân tích mã độc trên ứng dụng…
```

So với cùng câu hỏi chạy bằng mô hình giả — *"nội dung liên quan nằm ở các đoạn
được trích dẫn [1][2]"* — khác biệt là ở chỗ mô hình thật **trả lời câu hỏi**,
còn trích dẫn chỉ là chỗ dựa để kiểm chứng. Đó cũng là điều prompt ở
`app/services/prompt.py` yêu cầu, và nó chỉ kiểm chứng được khi có mô hình thật.

## Phát hiện đáng đưa vào báo cáo: bge-m3 rất nhạy với việc thiếu dấu

Cùng một câu hỏi, chỉ khác dấu:

| Câu hỏi | Điểm cross-encoder | Kết quả |
|---|---|---|
| `Phat hien tan cong mang dua tren Machine Learning thi lam nhung gi?` | **0.2705** | từ chối |
| `Phát hiện tấn công mạng dựa trên Machine Learning thì làm những gì?` | **0.9510** | trả lời |

Cùng một tài liệu, cùng ngưỡng τ = 0.35. Chỉ khác dấu tiếng Việt mà điểm chênh
**3,5 lần**, đủ để lật hẳn quyết định của cổng ngưỡng.

Điều này quan trọng vì người Việt gõ không dấu rất nhiều, nhất là trên điện
thoại. Nhánh từ khoá không bị ảnh hưởng — cấu hình `vi` có `unaccent` nên nó
khớp bình thường (quyết định 0001). Nhưng nhánh vector thì rơi mạnh, và
cross-encoder chấm trên câu hỏi gốc nên cũng rơi theo.

Ba hướng xử lý, chưa chọn:

1. Phục hồi dấu cho câu hỏi trước khi nhúng, rồi truy xuất bằng cả hai dạng.
2. Hạ τ — nhưng như vậy là hạ cho mọi câu hỏi, kể cả câu có dấu.
3. Coi đây là hạn chế và nêu trong báo cáo.

Việc này thuộc US-047 (hiệu chỉnh τ) và nên nhắc lại ở phần hạn chế của Chương 5.
Nó cũng là một luận điểm cụ thể cho việc dùng **truy xuất lai**: một nhánh hỏng
thì nhánh kia vẫn đỡ được.

## Năm lỗi thật, đều chỉ lộ ra khi chạy mô hình thật

### `EMBEDDING_REVISION=` buộc phải ra mạng ở mọi lần nạp mô hình

Một dòng bỏ trống trong `.env` đi vào cấu hình thành **chuỗi rỗng**, rồi được
truyền xuống HuggingFace như một revision thật. Nó không khớp bản trong cache
nên thư viện bắt buộc phải gọi mạng — kể cả khi mô hình đã nằm sẵn trên đĩa.

Hậu quả đúng bằng thứ US-029 AC-3 hứa là làm được: *"rút dây mạng, hệ thống vẫn
hỏi đáp đầy đủ"*. Đã có sẵn một validator biến chuỗi rỗng thành `None` cho ba
trường thiết bị; hai trường revision chỉ thiếu tên trong danh sách đó.

### `FlagEmbedding` vỡ với `transformers` 5

Thư viện của chính nhóm tác giả bge gọi `tokenizer.prepare_for_model`, một API
đã bị gỡ. Reranker chết ngay lượt chấm đầu tiên. Đã chuyển sang `CrossEncoder`
của `sentence-transformers` — nạp đúng mô hình đó, và thư viện này vốn đã có mặt
vì adapter nhúng cần. Bớt một phụ thuộc, và không phải ghim `transformers`
xuống bản cũ.

### Câu trả lời rỗng, không lỗi, không dấu vết

Câu hỏi qua cổng ngưỡng với điểm **0.9510** rồi trả về **không một token nào**.
Không ngoại lệ, không cảnh báo.

Nguyên nhân: Gemini đời mới "suy nghĩ" trước khi trả lời, và phần suy nghĩ ăn
vào **cùng hạn mức** `LLM_MAX_TOKENS`. Đo được: một câu hỏi nhỏ tốn 361 token
suy nghĩ cho 39 token trả lời. Với prompt RAG mang 8 đoạn tài liệu, suy nghĩ
dùng hết 1024 token và phần trả lời còn lại rỗng.

Đã sửa hai mặt: `thinkingBudget = 0` theo mặc định — câu trả lời ở đây phải rút
ra từ các đoạn đã cho chứ không phải suy luận ra — và luồng nào kết thúc mà
không phát ra chữ nào thì báo lỗi kèm `finishReason`, thay vì im lặng.

### Adapter Gemini gọi vào một SDK đã ngừng hỗ trợ

`google-generativeai` là thế hệ SDK đầu, nay đã ngừng, và **chưa từng được cài**
trên máy này. Fast Mode chưa bao giờ chạy được. REST endpoint thì không đổi, nên
đã gọi thẳng bằng `httpx` — đúng cách adapter cục bộ vẫn làm.

Cùng lượt đó: `httpx` chỉ được khai báo ở nhóm `dev`, trong khi adapter cục bộ
import nó lúc chạy. Dựng container từ phụ thuộc chính thì Privacy Mode chết ở
câu hỏi đầu tiên.

### 110/119 đoạn mang cùng một nhãn tiêu đề, và nhãn đó sai

Bộ nhận diện tiêu đề chỉ biết `Phần / Chương / Mục / Điều / Phụ lục`. Tài liệu
mẫu đánh số kiểu `2.13 Tên mục` và `Đề tài 2.10: …`, nên trong 85 trang chỉ đúng
một dòng lọt lưới — rồi nó bám vào mọi đoạn phía sau, kể cả đoạn cách nó ba mươi
trang.

Trên chip trích dẫn, một nhãn sai còn tệ hơn không có nhãn: người dùng bấm vào
và đọc một vị trí không có thật.

Đã sửa hai mặt:

- **Nhận diện rộng hơn** — thêm đánh số thập phân và `Đề tài / Bài / Câu /
  Nhiệm vụ`. Trên tài liệu thật: từ **1 tiêu đề** lên **47**, từ **1 nhãn cho
  110 đoạn** thành **45 nhãn khác nhau cho 141 đoạn**.
- **Không gán tiêu đề ở quá xa** — quá 20 000 ký tự thì tài liệu có cấu trúc mà
  bộ nhận diện không thấy, và gán bừa tiêu đề gần nhất phía trước là *nói sai*,
  không phải nói thiếu.

Ràng buộc tách `2.13 Phát hiện tấn công mạng` khỏi `2.5 kg mỗi ngày` là **chữ
hoa**: tiêu đề tiếng Việt viết hoa chữ đầu, số liệu giữa câu thì không. Chỉ đòi
"bắt đầu bằng chữ cái" là không đủ — cả hai đều qua được.

## Một tham số bị thiếu: chấm bao nhiêu ứng viên

`rerank()` chấm **toàn bộ** ứng viên sau RRF, khoảng 100 đoạn, và không có cách
nào giới hạn. Trên GPU thì không sao; trên CPU mỗi câu hỏi mất hàng phút.

Đã tách thành hai con số vốn khác nhau nhưng rất dễ nhầm thành một:

| | Ý nghĩa | Ảnh hưởng |
|---|---|---|
| `RERANK_CANDIDATES` | cross-encoder chấm bao nhiêu đoạn | độ trễ |
| `RERANK_TOP_K` | giữ lại bao nhiêu đoạn làm ngữ cảnh | chất lượng câu trả lời |

Gộp hai thứ này lại thì hạ chi phí cũng hạ luôn số đoạn đưa vào mô hình sinh —
tức là đổi cả chất lượng chứ không chỉ đổi tốc độ. Máy này đặt 15; mặc định của
đồ án vẫn là 50 và số đo báo cáo lấy từ máy đích với giá trị đó.

## Độ trễ trên CPU — chỉ để tham khảo

| Bước | Thời gian |
|---|---|
| Nhúng câu hỏi (bge-m3, CPU) | ~1 s |
| Xếp hạng lại 15 đoạn (CPU) | ~35 s |
| Sinh câu trả lời (Gemini) | ~15 s |
| **Tổng** | **~56 s** |

Xếp hạng lại chiếm phần lớn, đúng như dự đoán: cross-encoder chạy tuyến tính
theo số ứng viên và không có GPU thì mỗi cặp đều đắt. Đây chính là con số mà mô
hình hai máy ở `SPEC-v1.md` §10.0 sinh ra để giải quyết.

## Việc còn lại

- Chạy lại toàn bộ trên máy đích 16 GB với `DEFAULT_MODE=privacy` và
  `RERANK_CANDIDATES=50`. Mọi số đo trong báo cáo phải lấy từ đó.
- Hiệu chỉnh τ (US-047) — hiện 0.35 là giá trị khởi đầu, và ca thiếu dấu ở trên
  cho thấy nó đang chặt hơn mức nên có với một phần câu hỏi thật.
- Bộ tài liệu đánh giá vẫn cần văn bản pháp quy tiếng Việt thật; tài liệu mẫu
  hiện tại là danh sách đề tài môn học.
