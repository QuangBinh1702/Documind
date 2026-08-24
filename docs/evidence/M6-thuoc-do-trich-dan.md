# M6 — Sửa thước đo độ chính xác trích dẫn

**Ngày:** 2026-08-23 · **Liên quan:** US-045, US-014
**Script:** `eval/run_eval.py`

Lượt chạy thử 10 câu cho một kết quả bất thường: mọi chỉ số đều đạt, riêng
**citation accuracy 0,703 / ngưỡng 0,85**. Vì đó là chỉ số đo đúng luận điểm
trung tâm của đồ án — *"trả lời có trích dẫn kiểm chứng được"* — nên nó được
điều tra trước khi chạy đủ 130 câu.

Kết luận: **thước đo sai, không phải hệ thống sai.**

---

## 1. Dấu vết

Bốn câu trượt, kèm số marker mà câu trả lời đã dùng:

| Điểm | Số marker | Phân số |
|---|---|---|
| 0,20 | 5 | 1/5 |
| 0,25 | 4 | 1/4 |
| 0,25 | 4 | 1/4 |
| 0,33 | 3 | 1/3 |

Bốn con số khớp chính xác `1/N`. Đó không phải dấu vết của một hệ thống trích
dẫn sai — nó là dấu vết của một công thức **bị chặn trên bởi 1/N**.

## 2. Nguyên nhân

Công thức cũ:

```python
citation_accuracy = (số trích dẫn trùng đoạn vàng) / (tổng số trích dẫn)
```

Mỗi câu hỏi trong bộ dữ liệu gắn **đúng một** đoạn vàng. Nhưng bộ ngữ liệu gồm
quy chế đào tạo của **nhiều trường khác nhau** cùng bàn một chủ đề. Nên một câu
trả lời tốt sẽ trích dẫn nhiều nguồn — và bị phạt đúng vì đã làm thế.

Ví dụ, câu *"Sinh viên được xin nghỉ học tạm thời trong những trường hợp nào?"*
nhận về:

> Vì các tài liệu cung cấp có nhiều quy định khác nhau…
> **Theo đoạn [1] và [2]:** Được điều động vào lực lượng vũ trang [1][2]. Bị ốm,
> thai sản hoặc tai nạn phải điều trị dài ngày [1][2]. …
> **Theo đoạn [3]:** …

Câu trả lời này **đúng, đầy đủ, và trích dẫn chuẩn** cho từng nguồn. Nó nêu được
sự khác nhau giữa các quy chế — đúng thứ US-014 AC-4 yêu cầu (*"nếu các đoạn mâu
thuẫn nhau, nêu rõ sự khác biệt và trích dẫn cả hai"*). Thước đo cũ chấm nó
**0,20**.

Đây là **cùng một loại lỗi** đã gặp trước đó với `context_precision`: chỉ số bị
chặn trên bởi `1/top_k` nên không mẫu nào có thể qua ngưỡng. Loại lỗi này nguy
hiểm vì nó không làm gì đổ vỡ — nó chỉ cho ra một con số sai mà trông vẫn hợp lý.

## 3. Sửa như thế nào

Tách thành ba chỉ số, mỗi cái đo một câu hỏi khác nhau.

### `citation_accuracy` — chỉ số **cổng** (mới)

*"Mỗi lần gắn số, khẳng định đi kèm có nằm trong đúng đoạn mang số đó không?"*

Chấm bằng mô hình, và prompt nói rõ **không được trừ điểm vì trích dẫn nhiều
nguồn**. Đây mới là thứ đồ án hứa: bấm vào một số là ra đúng chỗ nội dung được
lấy.

### `citation_recall_gold` — tham khảo, tái lập tuyệt đối

*"Câu trả lời có trích dẫn đoạn chứa nhãn không?"* — 1,0 hoặc 0,0.

So khớp khoảng ký tự, không cần mô hình, nên chạy lại luôn ra cùng kết quả. Nó
trả lời câu hỏi *"hệ thống có tìm ra và trích dẫn đúng chỗ không"*, độc lập với
việc nó còn trích thêm gì.

### `citation_precision_gold` — giữ lại, KHÔNG làm cổng

Chính là công thức cũ. Giữ vì nó vẫn nói lên một điều: tỉ lệ trích dẫn tập trung
vào đúng đoạn vàng. Nhưng nó **không** đo được chất lượng trích dẫn trên một bộ
ngữ liệu có nhiều tài liệu chồng chủ đề, nên nó bị gỡ khỏi vai trò cổng.

---

## 4. Lỗi thứ hai: cách HỎI bộ chấm

Sau khi sửa định nghĩa, câu q001 vẫn bị chấm **4/24 = 0,167**. Lần này thủ phạm
không phải công thức mà là **cách đặt câu hỏi cho bộ chấm**.

Bản đầu đưa cả 8 đoạn (12 000 ký tự) cùng toàn bộ câu trả lời, rồi bảo mô hình
*"đếm xem bao nhiêu lần gắn số là đúng"* và trả về hai dòng. Đó là 24 phép đối
chiếu bắc chéo qua tám đoạn, gói vào một lượt trả lời hai con số.

### Đối chiếu: bộ chấm sai, không phải hệ thống sai

Đoạn [1] dài 1765 ký tự và **có chứa** toàn bộ thang điểm mà câu trả lời gán cho
nó: `3,6`, `4,0`, `3,2`, `3,59`, `2,5`, `3,19`, cùng `Xuất sắc`, `Giỏi`, `(GPA)`
và `(CPA)`. Nghĩa là những dòng bị chấm sai thật ra đúng.

> **Ghi lại một bước hụt trong quá trình điều tra**, vì nó đúng là bài học của
> mục này. Lần đọc đầu tiên tôi chỉ xem được phần đầu của đoạn — chỗ nói về khảo
> sát ý kiến người học và xếp hạng năm học theo tín chỉ — và kết luận ngược lại
> rằng đoạn [1] *không* có thang điểm. Phần thang điểm nằm phía dưới, ngoài
> khoảng đã đọc. **Đọc thiếu một đoạn cũng nguy hiểm y như tin một chỉ số**, và
> cách thoát ra là kiểm bằng một phép so khớp chính xác trên toàn văn thay vì
> bằng ấn tượng khi đọc lướt.

### Sửa: thu nhỏ việc của mỗi lượt gọi

Cả hai chỉ số cần mô hình chấm đều được viết lại theo cùng một nguyên tắc: **mô
hình chỉ trả lời Đ/S cho từng mục**, còn việc tách khẳng định do mã làm — tất
định và kiểm được.

* **Trích dẫn**: mỗi lượt gọi mang **một đoạn** và những khẳng định trích dẫn
  đoạn ấy.
* **Faithfulness**: khẳng định phải được đối chiếu với *mọi* đoạn, nên không thu
  về một đoạn được. Thay vào đó chia thành **cụm ba đoạn** (~5 000 ký tự mỗi
  lượt); một khẳng định chỉ cần một cụm xác nhận là đủ.

Đo lại trên cùng câu trả lời, cùng mô hình chấm:

| Câu | Chỉ số | Hỏi gộp | Hỏi chia nhỏ |
|---|---|---|---|
| q001 | citation | 0,167 | **0,893** |
| q001 | faithfulness | 0,167 | **0,966** |
| q002 | faithfulness | 1,000 | **0,714** |
| q003 | faithfulness | 1,000 | **1,000** |
| q004, q005 | faithfulness | 1,000 | **1,000** |

### Điểm đáng chú ý nhất: q002 đi NGƯỢC

Kiểu hỏi cũ chấm q002 là 1,000; kiểu mới chấm 0,714. Đây không phải bằng chứng
kiểu mới tệ hơn — nó là bằng chứng kiểu cũ **không đáng tin theo cả hai chiều**.

Lý do nằm ở dạng câu trả lời được yêu cầu. Kiểu cũ đòi một **con số đếm**
(`TỔNG: 14 / ĐƯỢC CHỨNG THỰC: 14`), mà một con số đếm thì trả lời cho xong rất
dễ và không có chỗ nào để lộ ra mô hình đã xét những gì. Kiểu mới đòi **một dòng
Đ/S cho từng mục**, nên mỗi mục đều phải được nêu ra và trả lời riêng.

Một chỉ số sai theo một chiều còn dò ra được. Sai theo **cả hai chiều** thì
không: nó cho ra những con số trông hợp lý ở mọi mẫu.

---

## 5. Điều này nói gì về phương pháp đánh giá

Đáng viết vào Chương 5 như một mục về **độ tin cậy của thước đo**, không giấu đi:

Một chỉ số tự động hỏng được theo **hai tầng độc lập**, và đồ án này gặp cả hai
trên cùng một con số:

1. **Định nghĩa sai** — công thức đo nhầm thứ. Dấu hiệu: một quy luật số học quá
   đều. `1/top_k` với `context_precision`, `1/N` với `citation_accuracy`.
2. **Cách hỏi sai** — định nghĩa đúng nhưng giao cho mô hình một việc quá tải,
   và nhận về một dạng trả lời không kiểm được. Dấu hiệu: điểm bất thường ở đúng
   những mẫu **dài và phức tạp nhất**, trong khi mẫu ngắn vẫn 1,0.

Tầng thứ hai nguy hiểm hơn vì nó **có vẻ hợp lý**: bộ chấm là một mô hình ngôn
ngữ, mô hình ngôn ngữ thì sai được, nên một điểm thấp trông như một kết quả chứ
không như một lỗi.

Rút ra một quy tắc dùng được cho mọi bộ chấm bằng mô hình:

> **Đừng bao giờ hỏi một con số tổng.** Bắt mô hình trả lời từng mục một, và để
> phần đếm cho mã. Con số tổng che mất việc mô hình đã xét những gì, nên nó vừa
> không kiểm được vừa dễ được trả lời cho xong.

Cách phát hiện cả hai đều giống nhau: **mở mẫu trượt ra đọc**, không nhìn con số
trung bình. Bốn câu bị chấm thấp nhất hoá ra là bốn câu trả lời tốt.

Đây chính là lý do US-059 tồn tại. Phần đối chiếu tay ở mục 4 là **một mẫu** của
việc đó, và nó đã đủ để lật ngược một kết luận. US-059 yêu cầu ≥ 30 mẫu; con số
ấy không phải thủ tục.

Ghi nhận thẳng: con số **0,703** đã từng được ghi vào `docs/evidence/` như một
kết quả trượt. Nó sai, và tài liệu này là bản đính chính.
