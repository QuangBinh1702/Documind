# Tài liệu tham khảo ngoài

Tài liệu của người khác, giữ lại để đối chiếu. **Không phải sản phẩm của đồ án này.**

| Tệp | Là gì | Dùng để làm gì |
|---|---|---|
| `luan-van-tham-khao-rag-da-tac-tu.docx` | Đồ án tốt nghiệp *"Xây dựng hệ thống số hoá và quản lý tri thức thông minh sử dụng kiến trúc RAG đa tác tử"* — Vương Ngọc Hậu, Võ Ngọc Huy · ĐH Bách khoa – ĐH Đà Nẵng · 06/2026 | Mẫu cấu trúc báo cáo 5 chương của khoa; mốc so sánh cho kết quả thực nghiệm |

## Vì sao giữ lại

Hệ thống trong luận văn này trùng khoảng **65% kiến trúc** với DocuMind (cùng RAG
trên tài liệu tiếng Việt, cùng hybrid retrieval + RRF + rerank, cùng ngăn xếp
FastAPI + Postgres + MinIO + Celery + Next.js). Nó có ích ở ba việc:

1. **Mẫu trình bày** — cấu trúc chương, cách đánh số hình/bảng, phần đầu báo cáo
   (xem `SPEC.md` US-054a AC-1 và AC-5).
2. **Mốc so sánh thực nghiệm** — Answer Relevancy 0.835 · Contextual Recall 0.742 ·
   Faithfulness 0.838 · pass rate toàn cục 50.4% trên 141 mẫu văn bản pháp quy
   tiếng Việt. Đây là căn cứ cho ngưỡng tối thiểu ở US-045 AC-2.
3. **Nguồn cảnh báo trùng lặp** — vì trùng nhiều, `SPEC.md` US-054a AC-3 yêu cầu
   một mục *"Điểm khác biệt so với các công trình liên quan"* trong Chương 1.
   Bốn điểm khác biệt: trích dẫn tới bbox · chạy offline hoàn toàn · ablation
   6 cấu hình · tách namespace cache.

## Quy tắc

- **Không sao chép nội dung** vào báo cáo. Đây là tài liệu để đối chiếu, không
  phải để mượn câu chữ.
- Khi trích dẫn số liệu của họ trong Chương 5, **ghi rõ nguồn** theo đúng định
  dạng IEEE ở `docs/references.md` (US-069).
