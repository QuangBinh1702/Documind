# Execution Plan: M0 — Spike khử rủi ro và nền móng repo

Date: 2026-08-21

## Status

Active

## Outcome

Ba giả định kiến trúc lớn nhất được kiểm chứng bằng số đo thật trên phần cứng
thật, mỗi kết quả có một decision record. Repo có bộ khung thư mục, git, và
quy ước bằng chứng sẵn sàng để bắt đầu M1.

Cụ thể, khi M0 xong ta biết chắc:

1. Bất biến offset (INV-1) có giữ được trên PDF tiếng Việt thật không.
2. Bốn mô hình có cùng nằm trong 16 GB VRAM không, và với runtime nào.
3. US-015 dừng ở bậc nào trong thang giảm cấp ba bậc.

## Context

- `SPEC.md` v2.2 — hành vi, 72 user story, mốc M0–M7, DoR/DoD ở Phần A.
- `SPEC-v1.md` v1.0 — kiến trúc, 4 bất biến §1.3, ERD + DDL §4, ngân sách VRAM §10.
- `SPEC-REVIEW.md` — căn cứ của các quyết định và việc còn lại.
- `docs/TOOLING.md` — hiện trạng codebase và kho công cụ.
- `docs/WORKFLOW.md` — cổng thẩm quyền và chuẩn hoàn thành của repo.

Phần cứng: phát triển trên laptop MX570 2 GB (`DEVICE=cpu`), đo hiệu năng trên
server riêng 16 GB VRAM.

## Scope

In scope:

- Ba spike S1/S2/S3 và ba decision record tương ứng.
- `git init`, `.gitignore`, bộ khung thư mục theo `SPEC-v1.md` §3.3.
- `docs/evidence/` với mẫu tệp bằng chứng.
- Chốt phiên bản chính xác của ngăn xếp (`SPEC-v1.md` §2 hiện là "đề xuất").
- Chốt `DEFAULT_MODE` là `privacy` hay `fast`.
- Chốt một skill frontend làm chuẩn.

Out of scope:

- Mọi mã sản phẩm. Spike là mã vứt đi, không mang vào `backend/` hay `frontend/`.
- Docker Compose đầy đủ — thuộc M1 (US-001).
- Schema thật trong Alembic — thuộc M1.

## Approach

1. **Dựng nền repo** — git, `.gitignore`, thư mục, `docs/evidence/`. *(Xong)*
2. **Viết ba spike script.** *(Xong)*
3. **Chuẩn bị mẫu** — đặt 3 PDF tiếng Việt vào `spikes/samples/`:
   một có lớp text sạch, một scan, một dùng mã cũ TCVN3/VNI nếu tìm được.
4. **Chạy S1 và S3 trên laptop** — cả hai không cần GPU.
5. **Chạy S2 trên server 16 GB** — cài torch bản CUDA trước.
6. **Ghi ba decision record** vào `docs/decisions/` theo `docs/templates/decision.md`.
7. **Cập nhật SPEC** nếu kết quả buộc phải đổi thiết kế.
8. **Xoá `spikes/`** sau khi đã ghi quyết định.

## Risks And Recovery

- **S1 đỏ (offset lệch).** Khả năng vừa, ảnh hưởng rất cao. Nguyên nhân hay gặp
  nhất là thứ tự ghép/chuẩn hoá: chuẩn hoá từng trang rồi ghép cho độ dài khác
  với ghép rồi chuẩn hoá. Spike đã in cảnh báo khi phát hiện lệch. Phục hồi:
  chốt một thứ tự duy nhất, dựng lại `page_map` trên chuỗi đã chuẩn hoá, thêm
  test hồi quy trước khi sang M1.
- **S2 cho thấy không đủ VRAM.** Khả năng thấp với 16 GB, nhưng nếu xảy ra thì
  phương án là nạp/giải phóng luân phiên embedding và LLM, hoặc lượng tử sâu hơn.
  Ghi vào decision record, cập nhật `SPEC-v1.md` §10.1.
- **S3 lệch highlight.** Khả năng vừa. Ba dạng lệch đã được phân biệt sẵn trong
  spike (gốc toạ độ / hệ số scale / xoay trang). Nếu không sửa được trong một
  ngày thì hạ US-015 xuống Bậc 2 và ghi rõ — SPEC đã cho phép sẵn ở AC-5.
- **Không tìm được PDF mã TCVN3/VNI.** Chấp nhận được. Ghi là chưa kiểm chứng,
  giữ US-007 AC-8 làm việc phải làm ở M1 chứ không xoá.

## Progress

- [x] `git init`, cấu hình user, nhánh `main`
- [x] `.gitignore` cho Python, Node, Docker, mô hình, bí mật, dữ liệu có bản quyền
- [x] Bộ khung thư mục theo `SPEC-v1.md` §3.3
- [x] `docs/evidence/` và mẫu tệp bằng chứng
- [x] `spikes/s1_offset.py`, `s2_vram.py`, `s3_highlight.py`, README, requirements
- [ ] Đặt 3 PDF mẫu vào `spikes/samples/`
- [ ] Chạy S1 → `spikes/out/s1_offset.md`
- [ ] Chạy S3 → mở `spikes/out/s3_highlight.html`, kiểm tra ở 3 mức zoom
- [ ] Chạy S2 trên server → `spikes/out/s2_vram.md`
- [ ] Decision record: bất biến offset và thứ tự chuẩn hoá
- [ ] Decision record: runtime LLM và ngân sách VRAM
- [ ] Decision record: bậc highlight của US-015
- [ ] Decision record: một skill frontend làm chuẩn
- [ ] Chốt phiên bản ngăn xếp, thay "đề xuất" ở `SPEC-v1.md` §2
- [ ] Chốt `DEFAULT_MODE`
- [ ] Xoá `spikes/` sau khi ghi xong quyết định

## Decisions

- 2026-08-21: Dùng hai cấu hình máy (laptop `DEVICE=cpu` / server `cuda`) thay vì
  phát triển trực tiếp trên server. Lý do: tránh phụ thuộc kết nối, và ép kiến
  trúc không hardcode thiết bị — một ràng buộc lành mạnh. Đã ghi vào
  `SPEC-v1.md` §10.0.
- 2026-08-21: Spike đặt trong `spikes/` tách khỏi `backend/`, và sẽ bị xoá.
  Lý do: mã spike tối ưu cho tốc độ trả lời câu hỏi, không cho chất lượng —
  để lẫn vào sản phẩm là cách nợ kỹ thuật hình thành.

Promote lasting product or architecture decisions into `docs/decisions/`.

## Validation

- Focused proof: `spikes/out/s1_offset.md` báo `ĐẠT` với 0 chunk lệch offset
  trên toàn bộ PDF mẫu; `s2_vram.md` có số đo thật của từng mô hình.
- Integration or end-to-end proof: `s3_highlight.html` mở được và ô highlight
  phủ đúng cụm từ ở ít nhất ba mức zoom khác nhau.
- Repository-required checks: chưa có bộ test repo ở M0 — sẽ thiết lập ở M1
  cùng với `test_offset_roundtrip` và `test_nfc_invariant`.

## Result

*Hoàn thành sau khi chạy đủ ba spike. Ghi kết quả kiểm chứng, hạn chế, và việc
phải chuyển sang M1 trước khi chuyển kế hoạch này sang `docs/plans/completed/`.*
