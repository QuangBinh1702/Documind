# 0001 Cách lập chỉ mục và truy vấn từ khoá cho tiếng Việt

Date: 2026-08-21

## Status

Accepted

## Context

`SPEC.md` US-009 AC-2 (bản v2.2) quy định lưu `tsvector` được sinh từ nội dung
**đã tách từ tiếng Việt, từ ghép nối bằng dấu gạch dưới** — ví dụ
`cơ_sở_dữ_liệu`. US-010 AC-2b yêu cầu câu hỏi phải được tách từ bằng đúng cùng
một hàm để hai đường index và query đối xứng.

Khi dựng Postgres và kiểm chứng thật, cách này **không hoạt động**:

```sql
SELECT to_tsvector('vi', 'cơ_sở_dữ_liệu quan_hệ');
-- 'co':1 'du':3 'he':6 'lieu':4 'quan':5 'so':2
```

Bộ phân tích của PostgreSQL coi dấu gạch dưới là **ký tự phân tách**. Từ ghép
bị vỡ thành từng âm tiết rời, đúng thứ mà việc tách từ sinh ra để tránh. Toàn
bộ công sức tách từ ở bước index bị vô hiệu hoá, và điều tệ nhất là nó **hỏng
im lặng** — không có lỗi nào được báo.

Đã thử ba hướng thay thế và đo kết quả thật trên Postgres 17.

## Decision

**Bỏ tách từ ở đường index. Dùng truy vấn cụm từ ở đường query.**

- **Index:** `to_tsvector('vi', content)` trên văn bản gốc đã chuẩn hoá NFC.
  Không tách từ, không gạch dưới.
- **Query:** tách từ câu hỏi bằng `underthesea`, rồi dựng truy vấn hỗn hợp —
  `phraseto_tsquery` cho mỗi cụm từ ghép, `plainto_tsquery` cho từ đơn, nối
  bằng `&&`.

```sql
-- Cụm từ ghép: yêu cầu các âm tiết LIỀN KỀ
phraseto_tsquery('vi','cơ sở dữ liệu')  -- 'co' <-> 'so' <-> 'du' <-> 'lieu'
```

## Alternatives Considered

1. **Giữ gạch dưới, dựng `tsvector` literal ở tầng ứng dụng.**
   Dạng `'cơ_sở_dữ_liệu':1 'quan_hệ':2`::tsvector có hoạt động — giữ nguyên từ
   ghép, giữ vị trí, `ts_rank_cd` trả về 0.1. Nhưng phải tự dựng chuỗi
   tsvector, tự xử lý bỏ dấu, và mọi lỗi ở khâu này lại hỏng im lặng. Phức tạp
   hơn nhiều mà không cho kết quả tốt hơn.

2. **`array_to_tsvector(ARRAY['cơ_sở_dữ_liệu', ...])`.**
   Giữ nguyên lexeme nhưng **mất thông tin vị trí**, nên `ts_rank_cd` trả về
   **0** cho mọi tài liệu. Không dùng được vì `ts_rank_cd` là hàm xếp hạng đã
   chọn cho nhánh từ khoá.

3. **Nối liền không dấu phân tách** (`cơsởdữliệu`).
   Cho một token sạch nhưng mất khả năng khớp bộ phận và không đọc được khi gỡ
   lỗi. Không có ưu điểm nào so với phương án đã chọn.

4. **Truy vấn AND thường (`plainto_tsquery`).**
   Đơn giản nhất nhưng cho kết quả sai: tài liệu *"cơ sở vật chất và dữ liệu
   thống kê"* **khớp** truy vấn *"cơ sở dữ liệu"* vì đủ bốn âm tiết nằm rải
   rác. `phraseto_tsquery` cho `false` ở đúng ca này.

## Consequences

Positive:

- **Rủi ro bất đối xứng tách từ gần như biến mất.** Đường index không tách từ
  gì cả, nên không có gì để lệch với đường query. Đây từng là rủi ro §B.5 của
  `SPEC-REVIEW.md`.
- **Độ chính xác đúng như mong muốn, đã đo:** cụm liền kề khớp (`true`), âm
  tiết rải rác không khớp (`false`).
- **Bỏ dấu hoạt động miễn phí.** Người dùng gõ `co so du lieu` vẫn khớp tài
  liệu viết `cơ sở dữ liệu` — nhờ `unaccent` trong cấu hình `vi`.
- **Mã hiệu văn bản hoạt động đúng** — ca mà US-010 AC-3 nêu là chỗ vector
  search thuần thất bại. `phraseto_tsquery('vi','TCVN 5945:2005')` sinh
  `'tcvn' <-> '5945' <-> '2005'` và khớp chính xác.
- **Index nhanh hơn và ít điểm hỏng hơn** — `underthesea` không còn nằm trên
  đường xử lý tài liệu, chỉ nằm trên đường xử lý câu hỏi.
- Nếu tách từ câu hỏi sai, hậu quả chỉ là truy vấn kém tối ưu cho câu hỏi đó,
  chứ không phải một chỉ mục rác tồn tại vĩnh viễn.

Tradeoffs:

- `underthesea` vẫn cần cho đường query, nên vẫn là phụ thuộc của hệ thống.
- Tất cả lexeme đều bị bỏ dấu, nên hai từ chỉ khác nhau ở dấu sẽ không phân
  biệt được ở nhánh từ khoá. Nhánh vector bù lại phần này.
- **Cần theo dõi:** `ts_rank_cd` trả về cùng giá trị `0.1` cho hai tài liệu
  khác nhau trong phép thử. Nếu điểm bị hoà nhiều, thứ hạng trở nên tuỳ tiện —
  mà RRF chỉ dùng thứ hạng. Phải kiểm tra lại ở M2 trên dữ liệu thật; nếu hoà
  nhiều thì cân nhắc `setweight` theo vùng văn bản hoặc đổi sang `ts_rank`.

## Follow-Up

- Cập nhật `SPEC.md` US-009 AC-2 và US-010 AC-1, AC-2b. *(Xong)*
- Cập nhật `SPEC-v1.md` §5.2. *(Xong)*
- Ở M2, đo phân bố điểm `ts_rank_cd` trên dữ liệu thật để phát hiện hoà điểm.
- Giữ cấu hình text search `vi` — nó vẫn là thứ cung cấp `unaccent`.
