# Bộ đánh giá — Chương 5 của báo cáo

Mọi con số trong Chương 5 sinh ra từ thư mục này. Nguyên tắc xuyên suốt: **chạy
lại phải ra cùng kết quả**, và mỗi con số phải truy được về cấu hình đã tạo ra nó.

## Quy trình

```
 1. tai_tai_lieu.py     tải tài liệu theo dataset/nguon.csv
 2. corpus_report.py    soi xem bộ đó thật sự gồm những gì
 3. build_dataset.py    nạp tài liệu + sinh bộ câu hỏi có nhãn      (US-044)
 4. review.py           NGƯỜI rà 100% câu hỏi                       (US-044 AC-6)
 5. run_eval.py         đo Recall · Precision · Faithfulness · …    (US-045)
 6. ablation.py         so sáu cấu hình A–F                         (US-046)
 7. tau_sweep.py        chọn ngưỡng τ bằng dữ liệu                  (US-047)
```

Bước 4 **không bỏ được**. Câu hỏi do mô hình sinh trông rất thuyết phục và phần
lớn là đúng, nhưng dạng hỏng hay gặp nhất — đáp án sai đúng một chi tiết — không
có cách nào phát hiện tự động, và nó làm hỏng mọi chỉ số tính từ đáp án đó.

## Bốn quyết định về phương pháp

Đây là những chỗ dễ làm sai mà kết quả vẫn trông bình thường.

**Câu hỏi sinh TỪ đoạn văn, không phải đi tìm đáp án.** Soạn câu hỏi trước rồi
tìm đoạn chứa đáp án nghe tự nhiên hơn, nhưng nếu dùng chính bộ truy xuất của hệ
thống để tìm thì bộ đánh giá đang tự chấm mình. Lấy đoạn ra trước rồi bảo mô hình
đặt câu hỏi cho đoạn đó thì ground truth đúng theo **cấu tạo**.

**Nhãn neo vào khoảng ký tự, không vào `chunk_id`.** `chunk_id` đổi mỗi lần nạp
lại. Chỉ cần đổi `CHUNK_TOKENS` một lần là toàn bộ nhãn mất giá trị — mà không có
gì báo lỗi, chỉ có điểm số tụt xuống. Nhãn neo vào `(tệp, char_start, char_end)`
trên văn bản gốc; một đoạn được tính là trúng khi nó **chồng lấn** khoảng đó.

**Câu ngoài phạm vi kiểm bằng nội dung, không bằng điểm.** Cách hiển nhiên là
loại câu nào có điểm rerank cao. Cách đó lọc bộ test bằng chính đại lượng mà bộ
test sinh ra để hiệu chỉnh: câu nào vô tình bị chấm cao sẽ bị vứt, nên phần còn
lại chỉ gồm ca hệ thống vốn đã làm tốt, và τ chọn ra sẽ đẹp hơn sự thật. Ở đây
hỏi một mô hình *"các đoạn này có trả lời được câu hỏi không?"* — độc lập với
thang điểm τ.

**Mô hình chấm khác mô hình sinh** (US-045 AC-9). Một mô hình chấm chính câu nó
vừa viết thì thiên vị theo hướng dễ đoán. Nếu buộc phải trùng, tệp kết quả ghi
thẳng điều đó vào mục `limitations`.

## Hạn chế đã biết của bộ câu hỏi

Phải nêu trong phần phương pháp, không giấu.

**Phân bố loại câu hỏi lệch.** Lượt sinh ngày 21/08/2026 cho 82 câu
`fact_single`, 17 `numeric`, 1 `inference`. US-044 AC-3 muốn phủ **năm** dạng,
trong đó có *cần tổng hợp nhiều đoạn* và *hỏi nối tiếp*.

Đây không phải lỗi cấu hình mà là **hệ quả trực tiếp của cách sinh**: câu hỏi
được đặt từ **một** đoạn để ground truth đúng theo cấu tạo, nên theo định nghĩa
nó không thể cần tới đoạn thứ hai. Câu nối tiếp cũng vậy — nó cần một lượt hội
thoại trước đó, mà ở đây không có.

Hai dạng còn thiếu cần cách sinh khác: lấy **cặp** đoạn cùng chủ đề rồi yêu cầu
một câu hỏi mà cả hai mới trả lời đủ, và sinh cặp câu hỏi nối tiếp nhau. Cả hai
làm được, chỉ là chưa làm.

Hệ quả cho việc đọc kết quả: Context Recall ở đây đo trên **ca dễ nhất** của
truy xuất — một đoạn duy nhất chứa trọn đáp án. Con số thật với câu hỏi cần tổng
hợp sẽ thấp hơn. Đừng trình bày nó như con số cho mọi loại câu hỏi.

**Đáp án có thể nằm ở nhiều tài liệu.** Sáu quy chế trong bộ nói những điều rất
giống nhau. Một câu hỏi chung chung có thể được trả lời đúng từ tài liệu khác,
và khi đó nhãn một-đoạn là quá hẹp: hệ thống trả lời đúng vẫn bị chấm là trượt.
Bước rà soát của con người là chỗ bắt những ca đó.

**Câu hỏi dễ hơn câu hỏi thật.** Đây là hạn chế nặng nhất, và nó là mặt trái
trực tiếp của điều làm cho ground truth đáng tin.

Câu hỏi được đặt **từ** một đoạn, nên nó thừa hưởng từ vựng của chính đoạn đó.
Truy xuất tìm lại đoạn ấy gần như chắc chắn: lượt chấm ngày 21/08/2026 cho điểm
cross-encoder **0.98–0.99** trên phần lớn câu trong phạm vi. Người dùng thật hỏi
bằng từ ngữ của họ, không phải từ ngữ của văn bản pháp quy.

Hệ quả: **Context Recall đo được ở đây là chặn trên, không phải kỳ vọng.** Nó
nói *"khi câu hỏi dùng đúng từ ngữ của tài liệu thì truy xuất tìm được"* — một
điều kiện yếu hơn nhiều so với điều người đọc báo cáo sẽ hiểu.

Ba việc thu hẹp khoảng cách đó, xếp theo mức đáng làm:

1. Buộc mô hình **diễn đạt lại**, cấm dùng lại cụm từ đặc trưng của đoạn.
2. Người rà viết lại những câu chép từ vựng quá sát — đây là một trong những
   việc chính của bước rà soát, không chỉ là kiểm đáp án đúng sai.
3. Thêm một nhóm câu hỏi do **người tự viết** mà không nhìn tài liệu, rồi mới
   đi tìm đoạn chứa đáp án. Ít câu cũng được: chúng là nhóm đối chứng cho biết
   khoảng cách giữa hai cách sinh là bao nhiêu, và chính con số đó mới là thứ
   đáng đưa vào phần bàn luận.

## Hai loại chỉ số, và vì sao phải tách ra

| Loại | Chỉ số | Tính chất |
|---|---|---|
| **So khớp** | Context Recall · Context Precision · Citation Accuracy | Chỉ so khoảng ký tự. Chạy lại luôn ra cùng con số, không ai cãi được |
| **Mô hình chấm** | Faithfulness · Answer Relevancy | Không có cách nào so chuỗi để biết một câu có bịa hay không. Đây là chỗ phương pháp yếu nhất của Chương 5 |

Trộn hai nhóm này vào một bảng làm người đọc tưởng chúng đáng tin như nhau.

Chỉ số **không đo được** ghi là `None`, không ghi `0`. Một lượt gọi hỏng không
phải là một câu trả lời bịa; gộp hai thứ đó lại là bóp méo số liệu theo hướng xấu
đi mà không có gì nói ra điều đó.

## Ràng buộc thực tế: chạy ở đâu

Cross-encoder trên CPU mất khoảng **35 giây mỗi câu hỏi**. Một lượt 100 câu là
gần một giờ, và bảng ablation có ba cấu hình dùng rerank.

| Việc | Laptop (CPU) | Máy đích (16 GB VRAM) |
|---|---|---|
| Sinh bộ câu hỏi | được | được |
| `run_eval.py` 100 câu | ~1 giờ | vài phút |
| `ablation.py` sáu cấu hình | ~3 giờ | ~20 phút |
| `tau_sweep.py` | ~1 giờ | vài phút |

Trên laptop hãy dùng `--so-cau 20` để kiểm chứng đường ống. **Số liệu cho báo cáo
phải chạy trên máy đích**, ở `DEFAULT_MODE=privacy` và `RERANK_CANDIDATES=50`.

Mọi script đều **ghi kết quả sau từng câu** và chạy tiếp được: mất điện giữa
chừng không xoá sạch công sức, chạy lại cùng lệnh sẽ bỏ qua phần đã xong.

## Hạn mức của Gemini bản miễn phí

Đo ngày 21/08/2026: `gemini-3.5-flash` chỉ cho **20 lượt gọi mỗi NGÀY** — đủ thử
vài câu, không đủ chạy một lượt đánh giá. Bản `flash-lite` cao hơn nhiều. Đây là
ràng buộc chi phối việc chọn mô hình ở đây, không phải chuyện chất lượng.

Nếu gặp 429 kéo dài: kiểm tra xem có tiến trình cũ nào còn chạy không. Dừng một
tác vụ nền không phải lúc nào cũng giết tiến trình con, và hai lượt chạy song
song thì tiêu gấp đôi hạn mức.

## Tệp sinh ra

| Tệp | Nội dung |
|---|---|
| `dataset/questions.json` | Bộ câu hỏi có nhãn kèm trạng thái rà soát |
| `results/<nhãn>.json` | Kết quả từng câu + siêu dữ liệu tái lập |
| `results/ablation.json` · `.svg` | Bảng và biểu đồ sáu cấu hình |
| `results/tau-sweep.json` · `.svg` | Bảng quét ngưỡng và biểu đồ đường |
| `results/tau-diem.json` | Điểm thô — để quét lại τ không phải chấm lại |

`results/` nằm trong `.gitignore` trừ `.gitkeep`: đây là số đo của một máy cụ thể
tại một thời điểm cụ thể, và số liệu cuối cùng đi vào báo cáo chứ không vào repo.
