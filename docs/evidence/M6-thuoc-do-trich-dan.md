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

## 4. Điều này nói gì về phương pháp đánh giá

Đáng viết vào Chương 5 như một mục về **độ tin cậy của thước đo**, không giấu đi:

* Một chỉ số tự động có thể sai theo hướng **phạt oan cái đúng**, và nó không tự
  báo. Cả hai lần trong đồ án này, dấu hiệu nhận ra đều là một **quy luật số học
  quá đều** — `1/top_k` lần trước, `1/N` lần này.
* Cách phát hiện là **đọc mẫu trượt**, không phải nhìn con số trung bình. Bốn câu
  trả lời bị chấm thấp nhất hoá ra là bốn câu trả lời tốt.
* Đây chính là lý do US-059 tồn tại: phải đối chiếu bộ chấm tự động với người
  chấm trước khi xây cả một chương lên nó.

Ghi nhận thẳng: con số **0,703** đã từng được ghi vào `docs/evidence/` như một
kết quả trượt. Nó sai, và tài liệu này là bản đính chính.
