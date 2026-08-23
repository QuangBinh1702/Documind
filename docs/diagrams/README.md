# Sơ đồ thiết kế

Mọi sơ đồ ở đây viết bằng **Mermaid**, dạng văn bản (US-060 AC-1). Lý do không
dùng ảnh vẽ tay: sơ đồ vẽ tay không đi cùng mã. Đến khi thiết kế đổi, ảnh nằm im
và không ai biết nó đã sai — còn tệp văn bản thì nằm trong cùng commit với thay
đổi tạo ra nó (AC-2), và diff của nó đọc được.

GitHub tự dựng hình mọi tệp `.mmd` khi mở xem, nên không cần công cụ gì để đọc.

## Xuất ảnh cho báo cáo

```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i docs/diagrams/03-erd.mmd -o docs/diagrams/hinh/03-erd.png -s 3
```

`-s 3` cho ảnh gấp ba độ phân giải mặc định — đủ nét để in (AC-4). Xuất SVG
(`-o ....svg`) thì nét ở mọi cỡ, dùng được nếu trình soạn báo cáo nhận SVG.

## Danh mục

### Chương 3 — Phân tích và thiết kế hệ thống

| Tệp | Nội dung |
|---|---|
| `03-pham-vi.mmd` | Phạm vi hệ thống và các tác nhân bên ngoài |
| `03-use-case.mmd` | Use case theo nhóm chức năng |
| `03-thanh-phan-logic.mmd` | Thành phần logic và luồng dữ liệu chính |
| `03-sequence-hoi-dap.mmd` | Một lượt hỏi đáp có trích dẫn, từ đầu tới cuối |
| `03-activity-cong-nguong.mmd` | Cổng ngưỡng τ quyết định trả lời hay từ chối |
| `03-activity-truy-xuat-lai.mmd` | Truy xuất lai: vector + BM25 → RRF → rerank |
| `03-state-nguon.mmd` | Vòng đời một nguồn tài liệu |
| `03-erd.mmd` | Lược đồ cơ sở dữ liệu |
| `03-bo-cuc-giao-dien.mmd` | Bố cục ba cột của màn hình làm việc |

### Chương 4 — Cài đặt

| Tệp | Nội dung |
|---|---|
| `04-thanh-phan-theo-lop.mmd` | Kiến trúc ports & adapters theo lớp |
| `04-activity-nap-tai-lieu.mmd` | Pipeline nạp tài liệu, kèm nhánh OCR |
| `04-sequence-xac-thuc.mmd` | Đăng nhập, làm mới token, đổi mật khẩu |
| `04-sequence-sse.mmd` | Luồng sự kiện SSE của một câu trả lời |
| `04-deployment.mmd` | Triển khai bằng Docker Compose |
