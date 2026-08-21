-- Khởi tạo Postgres cho DocuMind.
-- Chạy MỘT LẦN khi volume postgres còn rỗng, TRƯỚC khi Alembic chạy.
-- Tương ứng SPEC.md US-001 AC-8 và SPEC-v1.md §4.2.

CREATE EXTENSION IF NOT EXISTS vector;    -- kiểu vector + chỉ mục HNSW
CREATE EXTENSION IF NOT EXISTS citext;    -- email không phân biệt hoa thường
CREATE EXTENSION IF NOT EXISTS unaccent;  -- bỏ dấu cho full-text search
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- Cấu hình full-text search cho tiếng Việt.
--
-- PostgreSQL KHÔNG có từ điển tiếng Việt. Cách chuẩn là sao chép cấu hình
-- 'simple' rồi thêm unaccent, kết hợp với văn bản đã được TÁCH TỪ ở tầng ứng
-- dụng (underthesea nối từ ghép bằng '_', ví dụ cơ_sở_dữ_liệu).
--
-- Lưu ý về cách gọi tên trong báo cáo: đây KHÔNG phải BM25. ts_rank_cd là hàm
-- xếp hạng khác, không có tham số k1/b. Xem SPEC.md US-010 AC-1.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'vi') THEN
        CREATE TEXT SEARCH CONFIGURATION vi (COPY = simple);
        ALTER TEXT SEARCH CONFIGURATION vi
            ALTER MAPPING FOR asciiword, word, numword, asciihword, hword, numhword
            WITH unaccent, simple;
    END IF;
END
$$;

-- Kiểm chứng nhanh khi khởi động: nếu dòng nào lỗi, container sẽ báo ngay
-- thay vì để Alembic thất bại với thông báo khó hiểu ở bước sau.
DO $$
DECLARE
    v_probe tsvector;
BEGIN
    v_probe := to_tsvector('vi', 'cơ_sở_dữ_liệu quan_hệ');
    IF v_probe IS NULL THEN
        RAISE EXCEPTION 'Cấu hình text search "vi" không hoạt động';
    END IF;
    PERFORM '[1,2,3]'::vector;
    RAISE NOTICE 'DocuMind: extensions và cấu hình text search "vi" đã sẵn sàng';
END
$$;
