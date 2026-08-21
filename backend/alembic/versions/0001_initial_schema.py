"""Schema khởi tạo — toàn bộ bảng, chỉ mục và ràng buộc.

Revision ID: 0001
Create Date: 2026-08-21

Viết bằng SQL thô thay vì để Alembic tự sinh. Lý do: schema này có nhiều thứ
autogenerate xử lý kém — chỉ mục HNSW kèm tham số, GIN trên tsvector, kiểu
vector và citext, CHECK constraint, mảng UUID. DDL đã được rà soát ở
SPEC-v1.md §4.2; migration này chép lại đúng như vậy.
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extension và cấu hình text search 'vi' do infra/postgres/init tạo khi
    # container khởi động lần đầu. Lặp lại ở đây để chạy được cả khi dùng một
    # Postgres có sẵn không qua docker-compose.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'vi') THEN
                CREATE TEXT SEARCH CONFIGURATION vi (COPY = simple);
                ALTER TEXT SEARCH CONFIGURATION vi
                    ALTER MAPPING FOR asciiword, word, numword,
                                      asciihword, hword, numhword
                    WITH unaccent, simple;
            END IF;
        END
        $$;
        """
    )

    # ── Người dùng & phiên ──────────────────────────────
    op.execute(
        """
        CREATE TABLE users (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email         CITEXT NOT NULL UNIQUE,
            password_hash TEXT   NOT NULL,
            locale        TEXT   NOT NULL DEFAULT 'vi'
                          CHECK (locale IN ('vi','en')),
            role          TEXT   NOT NULL DEFAULT 'user'
                          CHECK (role IN ('user','admin')),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE refresh_tokens (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_refresh_active ON refresh_tokens (user_id) "
        "WHERE revoked_at IS NULL"
    )

    # ── Notebook ────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE notebooks (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title      TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_notebooks_user ON notebooks (user_id, updated_at DESC)"
    )

    # ── Nguồn ───────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE sources (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            notebook_id   UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
            title         TEXT NOT NULL,
            original_name TEXT NOT NULL,
            storage_key   TEXT NOT NULL,
            kind          TEXT NOT NULL
                          CHECK (kind IN ('pdf','docx','txt','md','image','paste')),
            mime_type     TEXT NOT NULL,
            size_bytes    BIGINT NOT NULL,
            page_count    INT,
            status        TEXT NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued','parsing','ocr','chunking',
                                            'embedding','ready','failed')),
            progress      SMALLINT NOT NULL DEFAULT 0
                          CHECK (progress BETWEEN 0 AND 100),
            is_scanned    BOOLEAN,
            ocr_engine    TEXT,
            text_quality  REAL,
            error_code    TEXT,
            error_message TEXT,
            in_scope      BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            ready_at      TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_sources_notebook ON sources (notebook_id, created_at DESC)"
    )
    # Chỉ mục bộ phận: worker quét nguồn kẹt ở trạng thái trung gian (US-021 AC-4)
    op.execute(
        "CREATE INDEX idx_sources_pending ON sources (status) "
        "WHERE status NOT IN ('ready','failed')"
    )

    # Văn bản chuẩn. char_start/char_end của MỌI chunk tính trên full_text này (INV-1).
    op.execute(
        """
        CREATE TABLE source_texts (
            source_id  UUID PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
            full_text  TEXT  NOT NULL,
            page_map   JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ── Đoạn tri thức ───────────────────────────────────
    op.execute(
        """
        CREATE TABLE source_chunks (
            id             BIGSERIAL PRIMARY KEY,
            source_id      UUID NOT NULL REFERENCES sources(id)   ON DELETE CASCADE,
            notebook_id    UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
            chunk_index    INT  NOT NULL,
            content        TEXT NOT NULL,
            context_prefix TEXT,
            heading_path   TEXT,
            page_no        INT,
            char_start     INT NOT NULL,
            char_end       INT NOT NULL,
            bbox           JSONB,
            token_count    INT NOT NULL,
            embedding      VECTOR(1024),
            tsv            TSVECTOR,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chunk_span_valid CHECK (char_end > char_start),
            CONSTRAINT chunk_unique_index UNIQUE (source_id, chunk_index)
        )
        """
    )
    op.execute("CREATE INDEX idx_chunks_notebook ON source_chunks (notebook_id)")
    op.execute(
        "CREATE INDEX idx_chunks_source ON source_chunks (source_id, chunk_index)"
    )
    op.execute("CREATE INDEX idx_chunks_tsv ON source_chunks USING GIN (tsv)")
    op.execute(
        "CREATE INDEX idx_chunks_embedding ON source_chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # ── Hội thoại ───────────────────────────────────────
    op.execute(
        """
        CREATE TABLE chat_sessions (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            notebook_id      UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
            title            TEXT NOT NULL,
            scope_source_ids UUID[],
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_sessions_notebook "
        "ON chat_sessions (notebook_id, updated_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE chat_messages (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id       UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role             TEXT NOT NULL CHECK (role IN ('user','assistant')),
            content          TEXT NOT NULL,
            answer_kind      TEXT CHECK (answer_kind IN ('grounded','no_answer',
                                                         'external','cached_external')),
            model_used       TEXT,
            condensed_query  TEXT,
            top_rerank_score REAL,
            latency_ms       INT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_messages_session ON chat_messages (session_id, created_at)"
    )

    # chunk_id dùng ON DELETE SET NULL: nguồn bị xoá thì chip vẫn hiện được
    # snippet đã chụp, kèm trạng thái "Nguồn đã bị xoá" (US-020 AC-4).
    op.execute(
        """
        CREATE TABLE message_citations (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id UUID   NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
            chunk_id   BIGINT REFERENCES source_chunks(id) ON DELETE SET NULL,
            marker     INT    NOT NULL,
            snippet    TEXT   NOT NULL,
            page_no    INT,
            CONSTRAINT citation_unique_marker UNIQUE (message_id, marker)
        )
        """
    )
    op.execute("CREATE INDEX idx_citations_message ON message_citations (message_id)")

    # ── Cache câu trả lời NGOÀI — namespace tách biệt ───
    #
    # INV-3: đường truy vấn tài liệu KHÔNG BAO GIỜ đọc bảng này. Không JOIN,
    # không UNION, không subquery. Nếu vi phạm, hệ thống sẽ dần trích dẫn chính
    # nội dung nó tự bịa ra và toàn bộ giá trị của tính năng trích dẫn sụp đổ.
    # Bảo vệ bằng test test_cache_never_in_retrieval (US-034 AC-7).
    op.execute(
        """
        CREATE TABLE external_answer_cache (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            question           TEXT NOT NULL,
            question_embedding VECTOR(1024) NOT NULL,
            answer             TEXT NOT NULL,
            model_used         TEXT NOT NULL,
            hit_count          INT  NOT NULL DEFAULT 0,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at         TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_cache_user ON external_answer_cache (user_id, expires_at)"
    )
    op.execute(
        "CREATE INDEX idx_cache_emb ON external_answer_cache "
        "USING hnsw (question_embedding vector_cosine_ops)"
    )
    op.execute(
        """
        CREATE TABLE external_call_log (
            id         BIGSERIAL PRIMARY KEY,
            user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            called_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            from_cache BOOLEAN NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_calls_user ON external_call_log (user_id, called_at DESC)"
    )

    # ── Chia sẻ ─────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE share_links (
            notebook_id UUID PRIMARY KEY REFERENCES notebooks(id) ON DELETE CASCADE,
            token       TEXT NOT NULL UNIQUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at  TIMESTAMPTZ
        )
        """
    )


def downgrade() -> None:
    # Thứ tự ngược với khoá ngoại.
    for table in (
        "share_links",
        "external_call_log",
        "external_answer_cache",
        "message_citations",
        "chat_messages",
        "chat_sessions",
        "source_chunks",
        "source_texts",
        "sources",
        "notebooks",
        "refresh_tokens",
        "users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # Cấu hình text search do migration này tạo thì migration này gỡ.
    # Extension để nguyên — có thể có thứ khác dùng chung database.
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS vi")
