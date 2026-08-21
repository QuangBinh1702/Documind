# Chuẩn bị dữ liệu kiểm thử

> **Hệ thống không cần huấn luyện mô hình nào.** Mọi mô hình đều dùng bản
> pre-trained tải về nguyên trạng: `bge-m3`, `bge-reranker-v2-m3`, Qwen3-8B,
> PaddleOCR. Tài liệu ở đây phục vụ **kiểm chứng và đánh giá**, không phải
> huấn luyện.

## 1. Tài liệu dùng cho việc gì

| Việc | Story | Cần bao nhiêu | Khi nào |
|---|---|---|---|
| Spike S1 — kiểm chứng bất biến offset | M0 | **3 tệp** | **Ngay bây giờ** |
| Spike S3 — kiểm chứng highlight theo bbox | M0 | dùng lại 3 tệp trên | Ngay bây giờ |
| Bộ test đánh giá RAGAS | US-044 | **5–10 tệp** | M6 |
| Dữ liệu demo | US-052 | 5 tệp đẹp | M7 |

**Tổng: khoảng 10 tệp là đủ cho toàn bộ đồ án.**

> 🔴 **Ba tệp cho spike là việc chặn.** Spike S1 kiểm chứng bất biến INV-1 —
> rủi ro số một theo `SPEC.md` §J.6. Không có tài liệu thật thì không chạy được,
> và mọi thứ xây trên nó vẫn còn là giả định.

---

## 2. Ba tệp cần ngay cho spike

| Tệp | Loại | Vì sao cần |
|---|---|---|
| `text.pdf` | PDF có lớp text sạch | Ca thường — offset phải khớp 100% |
| `scan.pdf` | PDF scan (ảnh, không có lớp text) | Kiểm tra đường OCR và cổng chất lượng |
| `legacy.pdf` | PDF dùng mã cũ TCVN3/VNI | Ca hỏng nguy hiểm nhất — xem §5 |

Không có `legacy.pdf` cũng chạy được, spike sẽ báo bỏ qua. Nhưng có được một
tệp như vậy là **rất quý**: nó là ca kiểm thử cho US-007 AC-8 mà hiện chưa có
gì để thử.

---

## 3. Nên lấy tài liệu gì

### Văn bản pháp quy và quy chế công khai

Ba lý do, xếp theo mức quan trọng:

1. **An toàn bản quyền.** Đưa được vào phụ lục báo cáo, không vướng gì. Giáo
   trình có bản quyền thì không.
2. **Đúng miền của bài toán.** Đây là loại tài liệu người ta thật sự cần tra
   cứu chính xác và cần kiểm chứng nguồn — đúng thứ DocuMind giải quyết.
3. **Có cấu trúc Chương / Điều / Khoản**, nên kiểm chứng được `heading_path`
   của US-008 AC-3.

Luận văn tham khảo trong `refs/` dùng đúng hướng này với 444 tệp văn bản pháp
quy giáo dục đại học.

### Nguồn lấy

| Nguồn | Có gì |
|---|---|
| `vanban.chinhphu.vn` | Nghị định, quyết định, thông tư |
| `vbpl.vn` (Bộ Tư pháp) | Cơ sở dữ liệu văn bản quy phạm pháp luật |
| `moet.gov.vn` | Văn bản ngành giáo dục — sát đề tài nhất |
| Trang quy chế của các trường đại học | Quy chế đào tạo, quy định học vụ, biểu mẫu |
| Cổng thông tin tỉnh/thành | Quyết định, công văn — nhiều bản **scan** |

---

## 4. Danh sách kiểm tra tính đa dạng

Với ~10 tệp, cần phủ đủ những thứ hệ thống phải xử lý. Thiếu dòng nào thì story
tương ứng không kiểm chứng được.

| Cần có | Ít nhất | Phục vụ story |
|---|---|---|
| PDF có lớp text sạch | 4 | US-007, spike S1 |
| **PDF scan** (không có lớp text) | 2 | US-023, US-024, US-048 |
| PDF dùng **mã cũ TCVN3/VNI** | 1 | US-007 AC-8 — nếu tìm được |
| DOCX | 1 | US-007 AC-3 |
| Ảnh chụp trang tài liệu | 1 | US-025 |
| Tài liệu có **bảng biểu** | 1 | US-044 AC-3, US-050 |
| Tài liệu có cấu trúc **Chương / Điều** | 4 | US-008 AC-3, `heading_path` |
| Tài liệu **ngắn** (dưới 5 trang) | 2 | Đối chứng — thường đạt điểm cao |
| Tài liệu **dài** (trên 30 trang) | 1 | Thử ngưỡng hiệu năng US-009 AC-4 |
| Tài liệu **tiếng Anh** | 1 | US-037 — hỏi tiếng Việt trên tài liệu tiếng Anh |

---

## 5. Tệp mã cũ TCVN3 — cách nhận biết

Dấu hiệu: mở bằng trình đọc PDF thấy chữ **bình thường**, nhưng copy ra Notepad
thì thành `C¬ së d÷ liÖu` thay vì `Cơ sở dữ liệu`.

Thường gặp ở văn bản số hoá những năm 2000–2010, hoặc văn bản scan rồi OCR bằng
phần mềm cũ.

Đây là ca nguy hiểm nhất vì nó **có lớp text đầy đủ** — US-023 đếm ký tự sẽ
thấy "đủ chữ" và cho qua, rồi hệ thống lập chỉ mục một tài liệu rác. Cổng chất
lượng US-056 sinh ra chính để chặn nó, và hiện chưa có tệp thật nào để kiểm
chứng bộ dò.

---

## 6. Cách đặt tệp

```
eval/dataset/documents/
├── quy-che/          # quy chế đào tạo các trường
├── thong-tu/         # thông tư, nghị định
├── quyet-dinh/       # quyết định, công văn ngắn
├── scan/             # PDF scan
├── bang-bieu/        # tài liệu có bảng
└── tieng-anh/        # tài liệu tiếng Anh
```

Thư mục này nằm trong `.gitignore` — tệp gốc **không commit**. Thay vào đó ghi
xuất xứ vào `eval/dataset/NGUON.md`. Bảng đó vào **phụ lục báo cáo**
(US-044 AC-7) và đủ để người khác tải lại đúng bộ dữ liệu.

### Tải tự động

`eval/dataset/nguon.csv` liệt kê URL; chạy:

```powershell
powershell -File eval\dataset\tai_tai_lieu.ps1
```

Script xác minh **theo nội dung tệp** (kiểm tra chuỗi `%PDF-`), không theo phần
mở rộng — cùng nguyên tắc với US-006 AC-5, vì nhiều trang trả về trang HTML báo
lỗi mang đuôi `.pdf`.

Trang nào chặn tải tự động thì tải tay từ trình duyệt rồi đặt vào đúng thư mục.

---

## 7. Ngoài tài liệu, cần chuẩn bị gì

Cho **M6** (đánh giá), chưa cần ngay:

- **100 câu hỏi có đáp án chuẩn** (US-044). Quy trình bán tự động: LLM sinh câu
  hỏi từ từng chunk → **người rà soát và sửa 100%** → ghi lại tỉ lệ loại và sửa
  (US-044 AC-6). Con số đó vào báo cáo như một phần của phương pháp.
- **30 câu hỏi ngoài phạm vi** (US-044 AC-4) — hợp lý về chủ đề nhưng chắc chắn
  không có đáp án trong kho. Chúng đo cổng ngưỡng τ ở US-047; không có thì
  US-013 AC-3 và US-047 đều không chạy được.
- **Khoá API cho bộ chấm RAGAS.** Lưu ý US-045 AC-9: **không dùng cùng model đã
  sinh câu trả lời để chấm** — đó là tự chấm điểm cho mình.

---

## 8. Thứ tự làm

1. **Thu 3 tệp** cho spike (§2) — việc chặn, làm ngay.
2. **Chạy spike S1 và S3** (`spikes/README.md`) — kiểm chứng offset và
   highlight trước khi xây tiếp.
3. Thu thêm cho đủ ~10 tệp theo §4, ghi `NGUON.md` ngay khi tải.
4. Đến **M6** mới soạn bộ 100 câu hỏi và 30 câu ngoài phạm vi.
