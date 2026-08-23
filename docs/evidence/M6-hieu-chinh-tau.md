# Hiệu chỉnh ngưỡng τ — số đo đầu tiên của đồ án

| | |
|---|---|
| Ngày | 2026-08-21 |
| Story | US-044, US-047 |
| Bộ test | 100 câu có đáp án + 30 câu ngoài phạm vi |
| Tài liệu | 6 quy chế đào tạo tiếng Việt, 376 đoạn |
| Nhúng · xếp hạng lại | `BAAI/bge-m3` · `BAAI/bge-reranker-v2-m3`, CPU |
| Sinh câu hỏi | `gemma4:31b` qua Ollama Cloud |

> **Bộ câu hỏi CHƯA được người rà soát.** US-044 AC-6 yêu cầu rà 100% trước khi
> số liệu dùng được cho báo cáo. Mọi con số dưới đây là của một bộ test do mô
> hình sinh, chưa qua tay người — chúng chứng minh **đường đo chạy đúng**, chưa
> chứng minh chất lượng hệ thống.

## Kết quả quét

| τ | Precision | Recall | F1 | TP | FP | FN | TN |
|---|---|---|---|---|---|---|---|
| 0.10 | 0.9009 | 1.0000 | 0.9479 | 100 | 11 | 0 | 19 |
| 0.25 | 0.9423 | 0.9800 | 0.9608 | 98 | 6 | 2 | 24 |
| **0.35** *(đang dùng)* | 0.9600 | 0.9600 | 0.9600 | 96 | 4 | 4 | 26 |
| 0.50 | 0.9694 | 0.9500 | 0.9596 | 95 | 3 | 5 | 27 |
| **0.65** *(F1 cao nhất)* | 0.9896 | 0.9500 | **0.9694** | 95 | 1 | 5 | 29 |
| 0.70 | 0.9896 | 0.9500 | 0.9694 | 95 | 1 | 5 | 29 |

Biểu đồ: `eval/results/tau-sweep.svg`.

## Kết luận: **giữ nguyên τ = 0.35**, không đổi sang 0.65

Đây là chỗ con số nói một đằng và cách đọc đúng nói một nẻo.

F1 chọn 0.65. Nhưng nhìn cả cột F1 thì nó **phẳng**: từ 0.9479 ở τ = 0.10 lên
0.9694 ở τ = 0.65 — chênh **0.02** trên toàn dải quét. Một cực trị nông như vậy
không phải là một lựa chọn được dữ liệu ủng hộ; nó là nhiễu.

Lý do nằm ở phân bố điểm:

| | dưới 0.1 | trên 0.9 | trung vị |
|---|---|---|---|
| Có đáp án (100) | 0 | **92** | 0.998 |
| Ngoài phạm vi (30) | **19** | 0 | 0.049 |

Hai nhóm **gần như không chồng lấn**. Với dữ liệu tách bạch đến thế, mọi ngưỡng
trong khoảng 0.1–0.7 đều cho kết quả gần như nhau, và F1 không có gì để chọn.

## Vì sao hai nhóm tách bạch bất thường

Không phải vì hệ thống tốt. Vì **câu hỏi được sinh TỪ chính đoạn văn** (US-044
AC-6), nên nó thừa hưởng từ vựng của đoạn đó và truy xuất tìm lại gần như chắc
chắn — trung vị 0.998.

Người dùng thật hỏi bằng từ ngữ của họ. Điểm của câu hỏi thật sẽ thấp hơn và
**tản hơn**, và khi đó τ = 0.65 sẽ từ chối oan rất nhiều câu lẽ ra trả lời được.
Chọn 0.65 dựa trên bộ test này là tối ưu hoá cho một bài toán dễ hơn bài toán
thật.

Đã sửa prompt sinh câu hỏi để buộc diễn đạt lại bằng từ ngữ đời thường. Nó thu
hẹp khoảng cách chứ không xoá được — xoá được thì cần nhóm câu hỏi do người tự
viết mà không nhìn tài liệu.

## Việc phải làm trước khi con số này vào báo cáo

1. **Rà 100% bộ câu hỏi** (`python eval/review.py`). Ghi lại tỉ lệ loại và tỉ lệ
   sửa — US-044 AC-6 yêu cầu đưa hai con số đó vào phần phương pháp.
2. Trong lúc rà, **viết lại những câu chép từ vựng quá sát** đoạn gốc. Đây là
   việc chính, không chỉ là kiểm đáp án đúng sai.
3. Thêm một nhóm nhỏ câu hỏi **do người viết mà không nhìn tài liệu**, rồi mới
   đi tìm đoạn chứa đáp án. Chênh lệch điểm giữa hai nhóm chính là số liệu đáng
   đưa vào phần bàn luận.
4. Quét lại τ sau khi rà. Nếu hai nhóm vẫn tách bạch như vậy thì kết luận trung
   thực là *"bộ test hiện tại không đủ khó để hiệu chỉnh τ"*, và nói thẳng điều
   đó có giá trị học thuật hơn một con số tối ưu giả.

## Đánh đổi vẫn phải nêu (US-047 AC-4)

- **τ thấp** — ở 0.10, **11/30** câu ngoài phạm vi vẫn được trả lời. Hệ thống
  nói về những thứ tài liệu không hề đề cập.
- **τ cao** — ở 0.70, **5/100** câu có đáp án bị từ chối oan.

Với một hệ thống lấy *"trả lời có trích dẫn kiểm chứng được"* làm điểm bán, từ
chối oan rẻ hơn bịa đặt. Đó là lý do nghiêng về τ cao **khi có dữ liệu ủng hộ** —
mà lần này thì chưa có.

## Ghi chú phương pháp

`tau_sweep.py` chấm mỗi câu **một lần** rồi quét ngưỡng bằng số học. Điểm
cross-encoder không phụ thuộc τ, nên chạy lại truy xuất cho từng giá trị sẽ tốn
gấp mười ba lần mà ra đúng cùng kết quả. Điểm thô lưu ở `eval/results/tau-diem.json`
— quét lại với dải khác không phải chấm lại.

Toàn bộ 130 câu mất **khoảng một giờ** trên CPU, gần như toàn bộ là cross-encoder.
Trên máy đích 16 GB con số này còn vài phút.
