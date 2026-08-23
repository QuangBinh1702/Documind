# M6 — Hiệu chỉnh ngưỡng bộ nhớ đệm

**Ngày đo:** 2026-08-23 · **Mô hình nhúng:** `BAAI/bge-m3`
**Script:** `eval/hieu_chinh_cache.py` · **Bộ mẫu:** `eval/dataset/cap_cache.json`
**Liên quan:** US-064, US-034

`EXTERNAL_CACHE_SIMILARITY` quyết định khi nào hệ thống trả lại một câu trả lời
đã lưu thay vì gọi API. Trước phép đo này nó là **0.93 — một giá trị đoán**.

---

## 1. Bộ mẫu

31 cặp câu hỏi có nhãn, chia ba nhóm. Nhóm giữa là nhóm quyết định:

| Nhóm | Số cặp | Ví dụ |
|---|---|---|
| Cùng ý, khác diễn đạt | 15 | *"Ai phát minh ra bóng đèn?"* ↔ *"Người phát minh ra bóng đèn là ai?"* |
| **Cùng khuôn, khác một chi tiết mang nghĩa** | 10 | *"Điều 5 quy định gì?"* ↔ *"Điều 15 quy định gì?"* |
| Không liên quan | 6 | *"Machine learning là gì?"* ↔ *"Bao nhiêu tín chỉ thì tốt nghiệp?"* |

Không có nhóm giữa thì phép đo vô nghĩa: cặp cùng ý và cặp ngẫu nhiên tách nhau
rất rõ, và mọi ngưỡng đều cho F1 gần 1.0.

---

## 2. Kết quả quét 0.85 → 0.97

| Ngưỡng | Precision | Recall | F1 | Cặp khác ý lọt qua |
|---|---|---|---|---|
| 0.85 | 0.750 | 0.800 | **0.774** | 4 |
| 0.89 | 0.818 | 0.600 | 0.692 | 2 |
| 0.92 | 0.750 | 0.400 | 0.522 | 2 |
| **0.93** *(đang dùng)* | 0.857 | 0.400 | 0.545 | **1** |
| **0.94** | **1.000** | 0.333 | 0.500 | **0** |
| 0.97 | 1.000 | 0.067 | 0.125 | 0 |

Đồ thị: `eval/results/hieu-chinh-cache.svg`

---

## 3. Kết luận: nâng lên **0.94**

### Vì sao không lấy F1 cao nhất

AC-2 của US-064 viết *"lấy ngưỡng theo F1 cao nhất"*. Áp dụng nguyên văn sẽ chọn
**0.85** — và ở ngưỡng đó có **bốn** cặp khác ý bị coi là trùng ý, trong đó có
đúng loại cặp mà chính phần mở đầu của US-064 nêu ra làm ví dụ nguy hiểm.

Đây là chỗ AC tự mâu thuẫn, và bảng số cho thấy vì sao. F1 coi hai chiều hỏng
là ngang nhau, còn ở đây chúng không ngang nhau chút nào:

* **Bỏ lỡ một lượt dùng lại** — tốn thêm một lần gọi API. Người dùng không nhận
  ra, và không có gì sai trong câu trả lời.
* **Dùng lại nhầm** — người hỏi về *học bổng loại giỏi* nhận về câu trả lời của
  *học bổng loại xuất sắc*, kèm dòng "câu trả lời đã lưu cho câu hỏi: …". Nếu
  họ không đọc kỹ dòng đó thì không có dấu hiệu nào khác.

Với một hệ thống có điểm bán là *"trả lời kiểm chứng được"*, chiều thứ hai đắt
hơn hẳn. **Chọn 0.94 — ngưỡng thấp nhất mà Precision đạt 1.000.**

Ghi nhận rõ: đây là **đi lệch khỏi AC-2**, có chủ ý, và lý do nằm trong chính dữ
liệu của phép đo.

### Cặp suýt lọt ở 0.93

```
0.9319   "Điều kiện xét học bổng loại giỏi?"
      ↔  "Điều kiện xét học bổng loại xuất sắc?"
```

Chỉ khác hai chữ, và hai câu trả lời là hai mức điểm khác nhau. Ngưỡng cũ để lọt
đúng ca này.

---

## 4. Phát hiện phụ, quan trọng cho Chương 5

**Tiếng Việt không dấu phá vỡ độ tương đồng ngữ nghĩa.**

```
0.3759   "dieu kien tot nghiep dai hoc la gi"
      ↔  "Điều kiện tốt nghiệp đại học là gì?"
```

Cùng **một câu**, chỉ khác dấu, mà cosine chỉ 0,376 — thấp hơn cả cặp *"Machine
learning là gì?"* ↔ *"Bao nhiêu tín chỉ thì tốt nghiệp?"*.

Điều này khớp với phát hiện đã đo ở phần truy xuất: cùng một câu hỏi, có dấu
được điểm rerank 0,9510 còn không dấu chỉ 0,2705. Hai phép đo độc lập, cùng một
kết luận: **`bge-m3` coi tiếng Việt không dấu gần như một ngôn ngữ khác.**

Hệ quả thực tế: không có ngưỡng cache nào bắt được ca này, và cũng không nên
tìm cách hạ ngưỡng để bắt — hạ tới 0,38 thì mọi cặp khác ý đều lọt. Đây là việc
của một bước **chuẩn hoá đầu vào** (thêm dấu tự động cho câu hỏi không dấu),
không phải việc của ngưỡng cache. Ghi vào hướng phát triển.

**Viết tắt cũng vậy, nhưng nhẹ hơn.** *"RAG"* ↔ *"Retrieval-Augmented
Generation"* chỉ đạt 0,577; *"GDP"* ↔ *"Tổng sản phẩm quốc nội"* đạt 0,881.

---

## 5. Giới hạn của phép đo

- **31 cặp là ít.** Đủ để loại một ngưỡng sai rõ ràng, không đủ để phân biệt
  0,94 với 0,95.
- **Nhãn do một người đặt.** Không có đồng thuận liên người chấm.
- **Bộ mẫu tự soạn**, cố ý nhồi các ca khó. Nó không phản ánh phân bố câu hỏi
  thật của người dùng — và đó là chủ đích: mục tiêu là tìm ngưỡng chặn được ca
  xấu nhất, không phải ước lượng tỉ lệ trúng trung bình.
- Con số phụ thuộc **mô hình nhúng**. Đổi `EMBEDDING_MODEL` là phải đo lại.
