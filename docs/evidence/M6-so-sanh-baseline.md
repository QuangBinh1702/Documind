# M6 — So sánh với công cụ thương mại

**Liên quan:** US-068
**Trạng thái:** phần bảng tính năng đã xong; phần chấm 20 câu **chưa làm** — xem
mục 4.

Câu hỏi *"so với NotebookLM thì sao?"* gần như chắc chắn sẽ được hỏi ở buổi bảo
vệ. Tài liệu này chuẩn bị câu trả lời, và nó cố ý trả lời theo hướng **hệ thống
này khác ở đâu**, không phải **hệ thống này tốt hơn**.

---

## 1. Bảng so sánh tính năng

| | **DocuMind** | **NotebookLM** | **ChatGPT (tải tệp)** |
|---|---|---|---|
| **Chạy hoàn toàn offline** | ✅ Privacy Mode, rút dây mạng vẫn hỏi được | ❌ dịch vụ đám mây | ❌ dịch vụ đám mây |
| **Tài liệu rời khỏi máy** | Chỉ khi người dùng chọn, và giao diện nói rõ | Luôn luôn | Luôn luôn |
| **Trích dẫn tới trang** | ✅ | ✅ | Không ổn định |
| **Trích dẫn tới vùng toạ độ trên trang** | ✅ `bbox` lưu từ lúc nạp, tô sáng đúng ô chữ | ❌ chỉ tới đoạn | ❌ |
| **Từ chối khi không đủ căn cứ** | ✅ cổng ngưỡng τ đứng **trước** lượt gọi mô hình | Có, nhưng do prompt | Hiếm |
| **OCR tiếng Việt tự chủ** | ✅ PP-OCRv5 chạy cục bộ | Đám mây, không kiểm soát | Đám mây |
| **Cấu hình được tham số truy xuất** | ✅ 15 tham số trong `.env`, mỗi cái là một trục ablation | ❌ hộp đen | ❌ hộp đen |
| **Đổi được mô hình nhúng / rerank / LLM** | ✅ mỗi cái sau một cổng | ❌ | ❌ |
| **Tách namespace bộ nhớ đệm** | ✅ INV-3 — câu trả lời sinh ra **không bao giờ** vào kho tri thức | Không công bố | Không áp dụng |
| **Chọn hỏi trong tài liệu nào** | ✅ | ✅ | Hạn chế |
| **Chia sẻ chỉ đọc kèm hỏi đáp** | ✅ | ✅ | ❌ |
| **Xuất hội thoại kèm danh mục trích dẫn** | ✅ Markdown và PDF | Hạn chế | Chép tay |
| | | | |
| **Chất lượng mô hình ngôn ngữ** | Phụ thuộc mô hình chạy được trên phần cứng có sẵn | Gemini bản mới nhất | GPT bản mới nhất |
| **Độ trễ** | Vài giây tới vài chục giây trên CPU | Nhanh | Nhanh |
| **Số định dạng nhận** | 8 | Nhiều hơn (Google Docs, Slides, YouTube, web) | Nhiều |
| **Chi phí vận hành** | Điện và phần cứng của bạn | Miễn phí (hiện tại) | Thuê bao |
| **Công sức cài đặt** | Docker + tải 10 GB mô hình | Mở trình duyệt | Mở trình duyệt |

### Đọc bảng này cho đúng

Bốn dòng cuối là chỗ **DocuMind thua**, và chúng nằm trong bảng vì bỏ chúng đi
thì bảng thành quảng cáo chứ không phải so sánh. Một công cụ thương mại có đội
ngũ, hạ tầng và mô hình mà một đồ án cá nhân không thể có.

Điều đồ án này chứng minh không phải *"làm tốt hơn NotebookLM"* mà là:
**một hệ thống RAG có kiểm soát, chạy trên phần cứng của chính người dùng, với
tài liệu tiếng Việt, là làm được — và mỗi tham số của nó đo được, giải thích
được, thay đổi được.**

Đó là thứ một hộp đen không cho phép, và cũng là thứ khiến hệ thống này dùng
được cho tài liệu **không được phép gửi ra ngoài** — hồ sơ nội bộ, tài liệu
chưa công bố, dữ liệu cá nhân.

---

## 2. Ba điểm khác biệt đáng nói nhất

### Cổng ngưỡng đứng trước lượt gọi mô hình

Phần lớn công cụ RAG lấy các đoạn liên quan nhất rồi **luôn luôn** đưa cho mô
hình, kèm chỉ thị *"chỉ trả lời từ ngữ cảnh"*. Chỉ thị đó là một lời đề nghị,
và mô hình có thể không nghe.

DocuMind chấm điểm liên quan bằng cross-encoder, so với ngưỡng τ, và **không gọi
mô hình** nếu không đạt. Mô hình không có cơ hội bịa vì nó không được hỏi. Câu
từ chối cũng vì thế mà đáng tin: nó tới từ một phép đo, không từ một quyết định
của mô hình.

### Trích dẫn tới vùng toạ độ, không chỉ tới trang

Toạ độ (`bbox`) được giữ suốt từ lúc trích xuất, qua chia đoạn, tới lúc hiển
thị. Đây là lý do bất biến INV-1 tồn tại và được kiểm trên **dữ liệu đã ghi vào
cơ sở dữ liệu** chứ không phải trên đối tượng trong bộ nhớ.

Với tài liệu scan cũng vậy: `OcrProvider` trả về toạ độ chứ không chỉ trả về
chữ, nên bản scan trích dẫn được ngang bản có lớp văn bản.

### Bộ nhớ đệm tách khỏi kho tri thức

Khi người dùng chủ động hỏi một câu ngoài tài liệu, câu trả lời được lưu vào
`external_answer_cache` — **một bảng khác**, và đường truy xuất tài liệu không
bao giờ đọc nó (INV-3).

Không tách thì hệ thống sẽ dần trích dẫn chính những nội dung nó tự sinh ra, và
toàn bộ giá trị của tính năng trích dẫn sụp đổ — chậm rãi, không có triệu chứng
nào cho tới khi quá muộn.

---

## 3. Giới hạn của phép so sánh này

- **Bảng lập bằng cách đọc tài liệu công khai và dùng thử**, không phải bằng
  benchmark chuẩn hoá.
- **Các công cụ thương mại thay đổi liên tục.** Bảng đúng tại thời điểm ghi;
  cần ghi ngày kiểm tra lại khi đưa vào báo cáo.
- **Không cùng mô hình nền.** DocuMind chạy mô hình vừa với phần cứng có sẵn;
  đối thủ chạy mô hình lớn nhất của họ. Chênh lệch chất lượng câu trả lời phần
  lớn đến từ đó, không từ kiến trúc RAG.

---

## 4. Phần chưa làm — cần người thực hiện

AC-2 đòi chạy **~20 câu** từ bộ test qua một công cụ bên ngoài rồi chấm thủ
công, đối chiếu độ chính xác và chất lượng trích dẫn.

Việc này **không tự động hoá được**: nó cần tải cùng bộ tài liệu lên NotebookLM
bằng tay, hỏi từng câu, và đọc từng câu trả lời để chấm.

Cách làm đề xuất:

1. Lấy 20 câu đầu trong phạm vi từ `eval/dataset/questions.json`.
2. Tải cùng bộ tài liệu lên công cụ đối chứng.
3. Hỏi từng câu, chép lại câu trả lời và trích dẫn nó đưa ra.
4. Chấm theo ba mức cho mỗi câu:
   - **Đúng và có trích dẫn kiểm chứng được**
   - **Đúng nhưng trích dẫn mơ hồ hoặc thiếu**
   - **Sai, hoặc bịa**
5. Đặt cạnh kết quả của DocuMind trên đúng 20 câu ấy.

Bảng ghi kết quả:

| # | Câu hỏi | DocuMind | Công cụ đối chứng | Ghi chú |
|---|---|---|---|---|
| 1 | | | | |
| … | | | | |

Khi trình bày phải nêu rõ: **20 câu là ít, chấm thủ công bởi một người, và hai
hệ thống không dùng cùng mô hình nền** (AC-3).
