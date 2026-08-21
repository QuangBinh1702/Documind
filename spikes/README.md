# Spike M0 — ba câu hỏi phải trả lời trước khi viết mã sản phẩm

Ba kịch bản trong thư mục này **không phải mã sản phẩm**. Chúng tồn tại để trả lời ba
câu hỏi có thể phá kiến trúc, rồi bị vứt đi (`SPEC.md` §J.1, mốc M0).

| Spike | Câu hỏi | Quyết định phụ thuộc |
|---|---|---|
| `s1_offset.py` | Cắt lại text bằng `char_start:char_end` trên PDF tiếng Việt thật có khớp 100% không? | Cách chunking và lưu text. Rủi ro số 1 của đồ án (J.6) |
| `s2_vram.py` | Bốn mô hình có cùng nằm trong 16 GB VRAM không? Với runtime nào? | Ollama hay vLLM. Chi phối M3 và M4 |
| `s3_highlight.py` | `bbox` từ PyMuPDF có vẽ đúng chỗ trên PDF.js không? | US-015 dừng ở Bậc 1, 2 hay 3 |

## Chuẩn bị

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux
source .venv/bin/activate

pip install -r spikes/requirements.txt
```

Đặt **3 tệp PDF tiếng Việt thật** vào `spikes/samples/`:

| Tên gợi ý | Loại | Vì sao cần |
|---|---|---|
| `text.pdf` | PDF có lớp text sạch | Ca thường — phải khớp 100% |
| `scan.pdf` | PDF scan (ảnh, không lớp text) | Kiểm tra đường OCR |
| `legacy.pdf` | PDF cũ dùng mã TCVN3/VNI nếu tìm được | Ca hỏng nguy hiểm nhất (§B.2) |

Không có `legacy.pdf` cũng chạy được — spike sẽ báo bỏ qua.

## Chạy

```bash
python spikes/s1_offset.py            # laptop cũng chạy được
python spikes/s2_vram.py              # PHẢI chạy trên server 16 GB
python spikes/s3_highlight.py         # laptop chạy được, xem kết quả trong trình duyệt
```

## Sau khi chạy

1. Kết quả nằm trong `spikes/out/`.
2. Ghi kết luận từng spike vào `docs/decisions/` theo mẫu `docs/templates/decision.md`.
3. Cập nhật `SPEC.md` nếu kết quả buộc phải đổi thiết kế.
4. **Xoá thư mục `spikes/`** sau khi đã ghi quyết định — mã spike không mang vào sản phẩm.
