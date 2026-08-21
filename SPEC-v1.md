# SPEC v1.0 — Kiến trúc, mô hình dữ liệu và hợp đồng API

| | |
|---|---|
| **Dự án** | DocuMind — Nền tảng hỏi đáp tài liệu có trích dẫn nguồn |
| **Vai trò tài liệu** | Đặc tả **kỹ thuật**. `SPEC.md` (v2.1) đặc tả **hành vi** qua user story và AC. Hai tài liệu bổ sung cho nhau |
| **Thuộc mốc** | M0 — phải chốt xong trước khi viết dòng code sản phẩm nào |
| **Phiên bản** | 1.0 |

> **Quy tắc dùng tài liệu này:** khi hành vi và kỹ thuật mâu thuẫn, `SPEC.md` thắng — tài liệu này mô tả *cách* làm, không định nghĩa *cái gì* phải làm.

---

# 1. Kiến trúc tổng thể

## 1.1 Sơ đồ thành phần

```mermaid
flowchart TB
    subgraph client["Trình duyệt"]
        UI["Next.js 15 · React 19<br/>3 cột: Nguồn · Hội thoại · Xem tài liệu"]
        PDFJS["PDF.js viewer<br/>highlight theo bbox"]
    end

    subgraph api["Dịch vụ API — FastAPI"]
        ROUTER["Router<br/>xác thực · validate · SSE"]
        SVC["Service<br/>nghiệp vụ"]
        PORTS["Ports<br/>giao diện trừu tượng"]
    end

    subgraph worker["Worker — Celery"]
        ING["Pipeline nạp tài liệu<br/>trích xuất → chunk → embed → index"]
    end

    subgraph adapters["Adapters"]
        EMB["EmbeddingProvider<br/>bge-m3"]
        RRK["RerankProvider<br/>bge-reranker-v2-m3"]
        LLM["LLMProvider<br/>Qwen3-8B cục bộ | Gemini Flash"]
        OCR["OCRProvider<br/>PaddleOCR"]
        EXT["Trích xuất<br/>PyMuPDF · python-docx"]
    end

    subgraph data["Lưu trữ"]
        PG[("PostgreSQL 17 + pgvector<br/>quan hệ · vector · full-text")]
        MINIO[("MinIO<br/>tệp gốc · tệp xuất")]
        REDIS[("Redis<br/>hàng đợi · rate limit")]
    end

    UI -->|HTTPS / SSE| ROUTER
    PDFJS -->|presigned URL| MINIO
    ROUTER --> SVC --> PORTS
    PORTS --> EMB & RRK & LLM
    SVC --> PG
    SVC -->|đẩy tác vụ| REDIS --> ING
    ING --> EXT & OCR & EMB
    ING --> PG & MINIO
```

## 1.2 Hai luồng xử lý

**Luồng A — nạp tài liệu** (bất đồng bộ, Celery):

```
Upload → MinIO → tạo bản ghi source (queued)
   ↓
trích xuất text  ─ PDF có lớp text → PyMuPDF
                 ─ PDF scan / ảnh  → OCR
                 ─ DOCX/TXT/MD     → parser tương ứng
   ↓
CHUẨN HOÁ NFC  ←── ranh giới duy nhất được phép chuẩn hoá
   ↓
lưu source_texts.full_text  (chuỗi chuẩn — mọi offset tính trên chuỗi này)
   ↓
chunking → char_start / char_end / page_no / bbox
   ↓
embedding (bge-m3, batch) + tsvector (đã tách từ)
   ↓
lưu source_chunks → source.status = ready
```

**Luồng B — hỏi đáp** (đồng bộ, streaming SSE):

```
câu hỏi + N lượt gần nhất
   ↓ condense → câu hỏi độc lập
   ├──────────────┬──────────────┐
vector search   full-text search  (song song, cùng lọc notebook_id + source_ids)
   └──────┬───────┘
        RRF (k=60) → top 50
          ↓
       rerank → top 5–8 + điểm sigmoid
          ↓
    max(điểm) ≥ τ ?
     ├── CÓ  → sinh câu trả lời grounded → gắn [n] → SSE
     └── KHÔNG → no_answer + nút mời hỏi ra ngoài (opt-in)
                    ↓ (nếu người dùng bấm)
              tra external_answer_cache → hit? trả ngay : gọi Gemini → lưu cache
```

## 1.3 Bốn bất biến kiến trúc

Đây là những ràng buộc **không được vi phạm ở bất kỳ đâu trong mã nguồn**. Mỗi bất biến có một test bảo vệ.

| # | Bất biến | Vì sao | Test bảo vệ |
|---|---|---|---|
| **INV-1** | `source_texts.full_text[chunk.char_start : chunk.char_end] == chunk.content` với **mọi** chunk | Toàn bộ tính năng trích dẫn đứng trên đẳng thức này | `test_offset_roundtrip` — US-008 AC-5 |
| **INV-2** | Mọi chuỗi text ghi vào DB đã qua `unicodedata.normalize("NFC", s)` | NFD làm lệch mọi offset và làm hỏng so khớp chuỗi highlight | `test_nfc_invariant` — chạy trên cả 3 đường trích xuất |
| **INV-3** | Đường truy vấn tài liệu **không bao giờ** đọc `external_answer_cache` — không JOIN, không UNION, không subquery | Nếu vi phạm, hệ thống sẽ trích dẫn chính nội dung nó tự bịa ra | `test_cache_never_in_retrieval` — US-034 AC-7 |
| **INV-4** | Mọi truy vấn dữ liệu người dùng lọc theo `user_id` ngay ở **tầng SQL**, không lọc sau khi đã lấy ra | Rò rỉ dữ liệu chéo người dùng | `test_cross_user_returns_404` — US-005 AC-5 |

---

# 2. Ngăn xếp công nghệ

Cột "Đề xuất" là điểm khởi đầu. **Chốt phiên bản chính xác ở M0** và ghim vào `pyproject.toml` / `package-lock.json`; ghi lại vào `docs/decisions/`.

| Lớp | Thành phần | Đề xuất | Vai trò |
|---|---|---|---|
| Ngôn ngữ | Python | 3.12 | Backend, worker |
| | TypeScript | 5.x | Frontend |
| API | FastAPI | 0.115+ | REST + SSE, OpenAPI tự sinh |
| | Pydantic + pydantic-settings | 2.x | Validate + cấu hình |
| | Uvicorn | latest | ASGI server |
| Dữ liệu | PostgreSQL | 17 | Quan hệ + vector + full-text — **một CSDL duy nhất** |
| | pgvector | 0.8+ | Kiểu `vector`, chỉ mục HNSW |
| | SQLAlchemy | 2.0 | ORM, cú pháp 2.0 |
| | Alembic | 1.13+ | Migration |
| Hàng đợi | Celery | 5.4+ | Xử lý tài liệu nền |
| | Redis | 7.4 | Broker + rate limit + cache tạm |
| Tệp | MinIO | latest | Tệp gốc, tệp xuất (tương thích S3) |
| Trích xuất | PyMuPDF | 1.24+ | PDF text + bbox + render trang |
| | python-docx / markdown-it | | DOCX, MD |
| OCR | PaddleOCR | 3.x | Chữ tiếng Việt trong ảnh/scan |
| NLP | underthesea | 6.x | Tách câu + tách từ tiếng Việt |
| Mô hình | `BAAI/bge-m3` | | Embedding 1024 chiều |
| | `BAAI/bge-reranker-v2-m3` | | Cross-encoder rerank |
| | Qwen3-8B (lượng tử 4-bit) | | LLM cục bộ — Privacy Mode |
| | Gemini Flash | | LLM ngoài — Fast Mode |
| Runtime LLM | **chốt ở spike S2** | Ollama *hoặc* vLLM | Xem §10 |
| Frontend | Next.js (App Router) | 15 | Giao diện |
| | React | 19 | |
| | PDF.js / react-pdf | | Xem PDF + highlight |
| | TanStack Query | 5 | Trạng thái máy chủ |
| | next-intl hoặc i18next | | Song ngữ VI/EN |
| Đánh giá | RAGAS | latest | 4 chỉ số RAG |
| | pytest | 8.x | Unit test |
| Vận hành | Docker Compose | v2 | Dựng toàn hệ thống |

> **Vì sao PostgreSQL + pgvector thay vì Qdrant/Milvus?** Một CSDL duy nhất giữ vector, full-text và quan hệ trong **cùng một transaction** — xoá một nguồn thì chunk, vector và chỉ mục biến mất cùng lúc, không có trạng thái lệch giữa hai kho. Đổi lại là mất một phần hiệu năng ở quy mô hàng chục triệu vector, điều không xảy ra trong phạm vi đồ án (ước tính < 200k chunk). Ghi lập luận này vào `docs/decisions/` — đây là câu hội đồng hay hỏi.

---

# 3. Kiến trúc phần mềm — Ports & Adapters

## 3.1 Nguyên tắc

Tầng nghiệp vụ **chỉ phụ thuộc vào giao diện trừu tượng** (port), không phụ thuộc vào thư viện cụ thể (adapter). Ba lợi ích trực tiếp cho đồ án:

1. **Ablation US-046 chạy được mà không sửa code** — bật/tắt một nhánh chỉ là đổi adapter qua config.
2. **Privacy Mode / Fast Mode** là hai adapter của cùng một port `LLMProvider` (US-030 AC-4).
3. Chương 2 của báo cáo có một mục lý thuyết thật (Hexagonal Architecture, Dependency Inversion).

## 3.2 Các port

```python
class EmbeddingProvider(Protocol):
    dim: int
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...

class RerankProvider(Protocol):
    def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        """Trả về [(chỉ số trong docs, điểm đã sigmoid về [0,1])], giảm dần."""

class LLMProvider(Protocol):
    name: str
    is_local: bool
    async def stream(self, system: str, messages: list[Msg], **kw) -> AsyncIterator[str]: ...

class OCRProvider(Protocol):
    def recognize(self, image: bytes) -> list[OCRLine]:
        """OCRLine: text, bbox (x0,y0,x1,y1), confidence."""

class TextExtractor(Protocol):
    def extract(self, path: Path) -> ExtractResult:
        """ExtractResult: full_text (NFC), pages: list[PageSpan], blocks: list[TextBlock]."""

class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def presigned_url(self, key: str, ttl_s: int) -> str: ...
    def delete(self, key: str) -> None: ...
```

## 3.3 Bố cục thư mục

```
documind/
├─ docker-compose.yml
├─ .env.example
├─ Makefile                      # make up / test / seed / eval
├─ backend/
│  ├─ pyproject.toml
│  ├─ alembic/versions/
│  └─ app/
│     ├─ main.py
│     ├─ settings.py             # TOÀN BỘ tham số — không hardcode ở nơi khác
│     ├─ api/                    # router: xác thực, validate, SSE. KHÔNG nghiệp vụ
│     │  ├─ auth.py  notebooks.py  sources.py  chat.py  stats.py  health.py
│     ├─ services/               # nghiệp vụ
│     │  ├─ auth.py  notebook.py  ingest.py  retrieval.py
│     │  ├─ answer.py  citation.py  cache.py
│     ├─ ports/                  # §3.2
│     ├─ adapters/
│     │  ├─ embedding/bge_m3.py
│     │  ├─ rerank/bge_reranker.py
│     │  ├─ llm/{local.py,gemini.py}
│     │  ├─ ocr/paddle.py
│     │  ├─ extract/{pdf.py,docx.py,plain.py}
│     │  └─ storage/minio.py
│     ├─ repositories/           # truy cập DB, nơi DUY NHẤT viết SQL
│     ├─ models/                 # SQLAlchemy
│     ├─ schemas/                # Pydantic
│     ├─ workers/
│     │  ├─ celery_app.py
│     │  └─ tasks/ingest.py
│     └─ text/                   # tiện ích tiếng Việt
│        ├─ normalize.py         # NFC — INV-2
│        ├─ segment.py           # tách từ/câu, dùng CHUNG cho index và query
│        └─ chunker.py
├─ frontend/
│  └─ src/{app,components,lib,locales}/
├─ eval/
│  ├─ dataset/{questions.json,out_of_scope.json}
│  ├─ run_ragas.py  run_ablation.py  calibrate_tau.py  measure_ocr.py
│  └─ results/
├─ docs/
│  ├─ decisions/  evidence/  diagrams/
└─ tests/
```

**Quy tắc phụ thuộc:** `api → services → ports`; `adapters → ports`; `repositories → models`. Không có mũi tên ngược. `services` **không được** `import` bất kỳ thứ gì từ `adapters`.

---

# 4. Mô hình dữ liệu

## 4.1 ERD

```mermaid
erDiagram
    users ||--o{ notebooks : "sở hữu"
    users ||--o{ refresh_tokens : ""
    users ||--o{ external_answer_cache : ""
    notebooks ||--o{ sources : ""
    notebooks ||--o{ chat_sessions : ""
    notebooks ||--o| share_links : ""
    sources ||--|| source_texts : ""
    sources ||--o{ source_chunks : ""
    chat_sessions ||--o{ chat_messages : ""
    chat_messages ||--o{ message_citations : ""
    source_chunks ||--o{ message_citations : "được trích dẫn"

    users {
        uuid id PK
        citext email UK
        text password_hash
        text locale
        text role
    }
    notebooks {
        uuid id PK
        uuid user_id FK
        text title
    }
    sources {
        uuid id PK
        uuid notebook_id FK
        text kind
        text status
        bool is_scanned
        text storage_key
    }
    source_texts {
        uuid source_id PK
        text full_text
        jsonb page_map
    }
    source_chunks {
        bigint id PK
        uuid source_id FK
        uuid notebook_id FK
        int page_no
        int char_start
        int char_end
        jsonb bbox
        vector embedding
        tsvector tsv
    }
    chat_messages {
        uuid id PK
        uuid session_id FK
        text role
        text answer_kind
        text model_used
    }
    message_citations {
        uuid id PK
        uuid message_id FK
        bigint chunk_id FK
        int marker
    }
    external_answer_cache {
        uuid id PK
        uuid user_id FK
        vector question_embedding
        int hit_count
    }
```

## 4.2 DDL

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- Cấu hình full-text cho tiếng Việt: PostgreSQL không có từ điển tiếng Việt.
-- Dùng 'simple' + unaccent, kết hợp với văn bản ĐÃ TÁCH TỪ ở tầng ứng dụng.
CREATE TEXT SEARCH CONFIGURATION vi (COPY = simple);
ALTER TEXT SEARCH CONFIGURATION vi
    ALTER MAPPING FOR asciiword, word, numword, asciihword, hword, numhword
    WITH unaccent, simple;

-- ─────────────────────────── Người dùng & phiên ───────────────────────────
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         CITEXT NOT NULL UNIQUE,
    password_hash TEXT   NOT NULL,                      -- argon2id
    locale        TEXT   NOT NULL DEFAULT 'vi' CHECK (locale IN ('vi','en')),
    role          TEXT   NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE refresh_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,                    -- KHÔNG lưu token gốc
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON refresh_tokens (user_id) WHERE revoked_at IS NULL;

-- ─────────────────────────────── Notebook ─────────────────────────────────
CREATE TABLE notebooks (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON notebooks (user_id, updated_at DESC);

-- ──────────────────────────────── Nguồn ───────────────────────────────────
CREATE TABLE sources (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notebook_id   UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,                        -- tên hiển thị, sửa được
    original_name TEXT NOT NULL,                        -- tên gốc, chỉ để hiển thị
    storage_key   TEXT NOT NULL,                        -- khoá MinIO — SINH NGẪU NHIÊN
    kind          TEXT NOT NULL CHECK (kind IN ('pdf','docx','txt','md','image','paste')),
    mime_type     TEXT NOT NULL,                        -- xác minh theo NỘI DUNG
    size_bytes    BIGINT NOT NULL,
    page_count    INT,
    status        TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','parsing','ocr','chunking','embedding','ready','failed')),
    progress      SMALLINT NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    is_scanned    BOOLEAN,
    ocr_engine    TEXT,
    text_quality  REAL,                                 -- điểm cổng chất lượng tiếng Việt
    error_code    TEXT,                                 -- mã ổn định, dùng để tra chuỗi i18n
    error_message TEXT,                                 -- tiếng Việt, hiển thị cho người dùng
    in_scope      BOOLEAN NOT NULL DEFAULT TRUE,        -- US-038
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    ready_at      TIMESTAMPTZ
);
CREATE INDEX ON sources (notebook_id, created_at DESC);
CREATE INDEX ON sources (status) WHERE status NOT IN ('ready','failed');

-- Văn bản chuẩn của nguồn. char_start/char_end của MỌI chunk tính trên full_text này.
CREATE TABLE source_texts (
    source_id  UUID PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
    full_text  TEXT  NOT NULL,        -- ĐÃ chuẩn hoá NFC (INV-2)
    page_map   JSONB NOT NULL,        -- [{"page":1,"start":0,"end":1873}, ...]
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ────────────────────────── Đoạn tri thức (lõi) ───────────────────────────
CREATE TABLE source_chunks (
    id             BIGSERIAL PRIMARY KEY,
    source_id      UUID NOT NULL REFERENCES sources(id)   ON DELETE CASCADE,
    notebook_id    UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,  -- phi chuẩn hoá, để lọc ở tầng SQL
    chunk_index    INT  NOT NULL,
    content        TEXT NOT NULL,        -- NFC. INV-1: == full_text[char_start:char_end]
    context_prefix TEXT,                 -- US-049; KHÔNG hiển thị khi trích dẫn
    heading_path   TEXT,                 -- "Chương 3 > 3.2 Chuẩn hoá dữ liệu"
    page_no        INT,
    char_start     INT NOT NULL,
    char_end       INT NOT NULL,
    bbox           JSONB,                -- [{"page":12,"x0":72.0,"y0":310.5,"x1":523.0,"y1":352.0}, ...]
    token_count    INT NOT NULL,
    embedding      VECTOR(1024),
    tsv            TSVECTOR,             -- sinh từ văn bản ĐÃ TÁCH TỪ (cơ_sở_dữ_liệu)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chunk_span_valid CHECK (char_end > char_start),
    UNIQUE (source_id, chunk_index)
);
CREATE INDEX idx_chunks_notebook  ON source_chunks (notebook_id);
CREATE INDEX idx_chunks_source    ON source_chunks (source_id, chunk_index);
CREATE INDEX idx_chunks_tsv       ON source_chunks USING GIN (tsv);
CREATE INDEX idx_chunks_embedding ON source_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- ────────────────────────────── Hội thoại ─────────────────────────────────
CREATE TABLE chat_sessions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notebook_id    UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
    title          TEXT NOT NULL,
    scope_source_ids UUID[],             -- US-038; NULL = toàn bộ nguồn
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON chat_sessions (notebook_id, updated_at DESC);

CREATE TABLE chat_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content         TEXT NOT NULL,
    answer_kind     TEXT CHECK (answer_kind IN ('grounded','no_answer','external','cached_external')),
    model_used      TEXT,
    condensed_query TEXT,               -- US-019 AC-5, phục vụ gỡ lỗi và báo cáo
    top_rerank_score REAL,              -- US-031 AC-4, dữ liệu hiệu chỉnh τ
    latency_ms      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON chat_messages (session_id, created_at);

CREATE TABLE message_citations (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID   NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    chunk_id   BIGINT REFERENCES source_chunks(id) ON DELETE SET NULL,  -- NULL = nguồn đã xoá (US-020 AC-4)
    marker     INT    NOT NULL,
    snippet    TEXT   NOT NULL,         -- chụp lại lúc trả lời, để còn hiện được khi nguồn bị xoá
    page_no    INT,
    UNIQUE (message_id, marker)
);
CREATE INDEX ON message_citations (message_id);

-- ───────────── Cache câu trả lời NGOÀI tài liệu — namespace TÁCH BIỆT ──────────────
-- INV-3: đường truy vấn tài liệu KHÔNG BAO GIỜ đọc bảng này.
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
);
CREATE INDEX idx_cache_user ON external_answer_cache (user_id, expires_at);
CREATE INDEX idx_cache_emb  ON external_answer_cache
    USING hnsw (question_embedding vector_cosine_ops);

CREATE TABLE external_call_log (
    id         BIGSERIAL PRIMARY KEY,
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    called_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    from_cache BOOLEAN NOT NULL
);
CREATE INDEX ON external_call_log (user_id, called_at DESC);

-- ────────────────────────────── Chia sẻ ───────────────────────────────────
CREATE TABLE share_links (
    notebook_id UUID PRIMARY KEY REFERENCES notebooks(id) ON DELETE CASCADE,
    token       TEXT NOT NULL UNIQUE,    -- ngẫu nhiên ≥ 32 ký tự
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ
);
```

## 4.3 Ghi chú thiết kế

**`notebook_id` phi chuẩn hoá trong `source_chunks`** — cố ý. Nhánh vector search phải lọc theo notebook **ngay trong câu truy vấn HNSW**; nếu phải JOIN sang `sources` thì mất khả năng dùng chỉ mục hiệu quả.

**`bbox` là mảng, không phải một hộp** — một chunk thường trải nhiều dòng, mỗi dòng một hộp. Highlight vẽ tất cả các hộp trong mảng.

**`message_citations.snippet` lưu bản chụp** — khi nguồn bị xoá, `chunk_id` thành `NULL` nhưng chip vẫn hiển thị được nội dung và trạng thái *"Nguồn đã bị xoá"* (US-020 AC-4).

**`error_code` tách khỏi `error_message`** — code là mã ổn định (`PDF_ENCRYPTED`, `OCR_EMPTY`) để tra chuỗi i18n; message là bản tiếng Việt đã dựng sẵn. Không hardcode tiếng Việt trong tầng service.

**Cảnh báo HNSW + lọc:** pgvector lọc *sau* khi duyệt đồ thị. Nếu notebook chỉ có vài nguồn trong khi bảng có hàng trăm nghìn chunk, kết quả có thể trả về thiếu. Đặt `hnsw.ef_search` đủ lớn (mặc định 40 → nâng lên 100–200) và **luôn kiểm tra số kết quả trả về**; nếu thiếu, dùng chỉ mục IVFFlat hoặc thêm điều kiện lọc trước. Ghi nhận điểm này vào `docs/decisions/`.

---

# 5. Truy vấn retrieval

## 5.1 Nhánh vector

```sql
SELECT id, source_id, page_no, content,
       1 - (embedding <=> :qvec) AS score
FROM   source_chunks
WHERE  notebook_id = :notebook_id
  AND  (:source_ids IS NULL OR source_id = ANY(:source_ids))
ORDER  BY embedding <=> :qvec          -- <=> là khoảng cách cosine
LIMIT  :top_n;                          -- mặc định 50
```

## 5.2 Nhánh từ khoá

> **Lưu ý phát biểu:** PostgreSQL **không có BM25**. `ts_rank_cd` là hàm xếp hạng khác — có trọng số theo mật độ và vị trí, không có tham số `k1`/`b`. Điều này **không ảnh hưởng đến kết quả hợp nhất**, vì RRF chỉ dùng **thứ hạng**, không dùng điểm gốc. Trong báo cáo phải gọi đúng tên: *"truy xuất từ khoá bằng full-text search của PostgreSQL"*, không gọi là BM25.

```sql
SELECT id, source_id, page_no, content,
       ts_rank_cd(tsv, query) AS score
FROM   source_chunks,
       to_tsquery('vi', :segmented_query) AS query   -- ĐÃ tách từ, cùng hàm với lúc index
WHERE  notebook_id = :notebook_id
  AND  (:source_ids IS NULL OR source_id = ANY(:source_ids))
  AND  tsv @@ query
ORDER  BY score DESC
LIMIT  :top_n;
```

**Bất đối xứng tách từ là lỗi im lặng nguy hiểm nhất ở bước này.** Cùng một hàm `segment()` phải dùng cho cả lúc index và lúc truy vấn. Có unit test khẳng định điều đó.

Sinh `tsv` lúc index:

```python
tsv = func.to_tsvector('vi', segment(chunk.content))   # "cơ_sở_dữ_liệu quan_hệ ..."
```

## 5.3 RRF

```python
def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """rankings: mỗi phần tử là danh sách chunk_id đã sắp theo thứ hạng."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores
```

`k = 60` là giá trị chuẩn trong tài liệu gốc của Cormack et al. (2009). Nằm trong config (`RRF_K`), là một trục có thể quét thêm nếu còn thời gian.

## 5.4 Rerank và cổng ngưỡng

```python
pairs  = [(query, c.content) for c in candidates]        # 50 ứng viên sau RRF
logits = reranker.compute_score(pairs, normalize=True)   # normalize=True → sigmoid → [0,1]
top    = sorted(zip(candidates, logits), key=lambda x: -x[1])[:settings.RERANK_TOP_K]

if top[0][1] >= settings.TAU:      # TAU tính trên thang ĐÃ sigmoid
    return grounded_path(top)
return no_answer_path(top[0][1])   # lưu top_rerank_score để hiệu chỉnh τ ở US-047
```

**`normalize=True` là bắt buộc.** Không có nó, `compute_score` trả logit thô (khoảng −10…+10) và ngưỡng `τ = 0.35` trở nên vô nghĩa.

---

# 6. Hợp đồng API

Tiền tố `/api`. Xác thực: `Authorization: Bearer <access_token>`.

## 6.1 Quy ước lỗi

```json
{ "error": { "code": "SOURCE_TOO_LARGE", "message": "Tệp vượt quá giới hạn 50 MB.", "details": {"limit_mb": 50} } }
```

| Mã HTTP | Khi nào |
|---|---|
| `400` | Dữ liệu vào không hợp lệ |
| `401` | Thiếu / hết hạn token |
| `404` | Không tồn tại **hoặc không thuộc về người dùng hiện tại** — không dùng `403` cho tài nguyên của người khác (INV-4) |
| `409` | Xung đột trạng thái (ví dụ xử lý lại nguồn đang chạy) |
| `413` | Tệp quá lớn |
| `415` | Định dạng không hỗ trợ |
| `429` | Vượt giới hạn (đăng nhập sai, quota gọi ngoài) |
| `422` | Vi phạm ràng buộc nghiệp vụ (ví dụ notebook đã đủ 50 nguồn) |

`message` **luôn** là tiếng Việt hoặc tiếng Anh theo `Accept-Language`; **không bao giờ** chứa traceback.

## 6.2 Xác thực

| Method | Đường dẫn | Vào | Ra |
|---|---|---|---|
| POST | `/auth/register` | `{email, password}` | `{access_token, refresh_token, user}` |
| POST | `/auth/login` | `{email, password}` | như trên · `429` sau 5 lần sai trong 5 phút |
| POST | `/auth/refresh` | `{refresh_token}` | `{access_token, refresh_token}` — **xoay vòng**, token cũ bị thu hồi |
| POST | `/auth/logout` | `{refresh_token}` | `204` |
| POST | `/auth/change-password` | `{old_password, new_password}` | `204` · thu hồi **toàn bộ** refresh token |
| GET | `/auth/me` | — | `{id, email, locale, role}` |
| PATCH | `/auth/me` | `{locale}` | `{...}` |

Access token 60 phút · refresh token 7 ngày · mật khẩu băm bằng **argon2id**.

## 6.3 Notebook

| Method | Đường dẫn | Ghi chú |
|---|---|---|
| GET | `/notebooks` | `[{id, title, source_count, updated_at}]` |
| POST | `/notebooks` | `{title}` |
| GET | `/notebooks/{id}` | |
| PATCH | `/notebooks/{id}` | `{title}` |
| DELETE | `/notebooks/{id}` | Xoá dây chuyền: source, chunk, session **và tệp trên MinIO** |

## 6.4 Nguồn

| Method | Đường dẫn | Ghi chú |
|---|---|---|
| POST | `/notebooks/{id}/sources` | `multipart/form-data`. Trả về **< 2 s** với `{source_id, status:"queued"}`. MIME xác minh theo **nội dung** |
| POST | `/notebooks/{id}/sources/paste` | Ảnh clipboard (base64) hoặc text thuần |
| GET | `/notebooks/{id}/sources` | |
| GET | `/notebooks/{id}/sources/events` | **SSE** — tiến độ xử lý (§7.2) |
| GET | `/sources/{id}` | Kèm `status`, `progress`, `error_code`, `error_message` |
| GET | `/sources/{id}/file` | `302` tới presigned URL của MinIO, TTL 5 phút |
| GET | `/sources/{id}/text` | Text đã trích, phục vụ US-027 và viewer của DOCX/TXT |
| PATCH | `/sources/{id}/text` | Sửa text OCR → **chỉ chunk bị ảnh hưởng** được xử lý lại |
| PATCH | `/sources/{id}` | `{title, in_scope}` |
| POST | `/sources/{id}/retry` | Đưa lại vào hàng đợi |
| POST | `/sources/{id}/force-ocr` | Ép OCR toàn bộ, bỏ qua phân loại tự động |
| DELETE | `/sources/{id}` | Xoá chunk, vector **và tệp MinIO** |

Giới hạn: tệp ≤ **50 MB** · ảnh ≤ **10 MB** · ≤ **50 nguồn** mỗi notebook · định dạng `pdf, docx, txt, md, png, jpg, jpeg, webp`.

## 6.5 Hội thoại

| Method | Đường dẫn | Ghi chú |
|---|---|---|
| GET | `/notebooks/{id}/sessions` | |
| POST | `/notebooks/{id}/sessions` | Tiêu đề tự sinh từ câu hỏi đầu tiên |
| PATCH | `/sessions/{id}` | `{title, scope_source_ids}` |
| DELETE | `/sessions/{id}` | Không ảnh hưởng nguồn |
| GET | `/sessions/{id}/messages` | Kèm đầy đủ citation để dựng lại chip |
| POST | `/sessions/{id}/ask` | `{question, mode:"privacy"\|"fast"}` → **SSE** (§7.1) |
| POST | `/sessions/{id}/ask-external` | `{question, confirmed:bool}` → **SSE**. Chỉ gọi khi người dùng bấm nút |
| POST | `/sessions/{id}/stop` | Huỷ sinh; phần đã sinh vẫn được lưu |
| GET | `/citations/{chunk_id}` | `{content, page_no, char_start, char_end, bbox, source:{id,title,kind}}` |
| POST | `/sessions/{id}/export?format=md\|pdf` | Trả tệp; PDF dùng font Unicode (DejaVu/Noto) |

## 6.6 Khác

| Method | Đường dẫn | Ghi chú |
|---|---|---|
| GET | `/health` | `{status, postgres, redis, minio, gpu, models_loaded}` — **không cần xác thực** |
| GET | `/stats` | Số liệu US-041; chỉ `role = admin` |
| DELETE | `/cache` | Xoá toàn bộ cache của người dùng hiện tại |
| DELETE | `/cache/{id}` | Xoá một mục |
| POST | `/notebooks/{id}/share` | Sinh token ≥ 32 ký tự |
| DELETE | `/notebooks/{id}/share` | Thu hồi → link cũ trả `404` |
| GET | `/shared/{token}` | Truy cập chỉ đọc, không cần đăng nhập |

---

# 7. Hợp đồng sự kiện SSE

> Đây là hợp đồng mà **cả backend lẫn frontend đều phụ thuộc**. Đổi nó sau khi đã code là tốn kém — chốt ở M0.

## 7.1 Luồng trả lời — `POST /sessions/{id}/ask`

`Content-Type: text/event-stream`. Mỗi sự kiện là một dòng `data: <JSON>`.

| `type` | Payload | Khi nào |
|---|---|---|
| `meta` | `{message_id, mode, model}` | Ngay khi bắt đầu |
| `status` | `{stage}` — `condensing`, `retrieving`, `reranking`, `generating` | Chuyển bước; frontend hiện chỉ báo |
| `token` | `{text}` | Mỗi mẩu văn bản được sinh |
| `citation` | `{marker, chunk_id, source_id, source_title, page, char_start, char_end, snippet}` | Khi một marker được xác định |
| `no_answer` | `{top_score, threshold}` | Cổng ngưỡng chặn → frontend hiện nút hỏi ra ngoài |
| `done` | `{message_id, answer_kind, latency_ms, model_used}` | Kết thúc |
| `error` | `{code, message}` | Lỗi giữa chừng; message là tiếng Việt |

```
data: {"type":"meta","message_id":"7f3a...","mode":"privacy","model":"qwen3-8b-q4"}
data: {"type":"status","stage":"retrieving"}
data: {"type":"token","text":"Dạng chuẩn 3NF yêu cầu"}
data: {"type":"citation","marker":1,"chunk_id":48210,"source_id":"a1b2...",
       "source_title":"Giáo trình CSDL","page":47,"char_start":91204,"char_end":91802,
       "snippet":"Một quan hệ ở dạng chuẩn 3 khi..."}
data: {"type":"done","message_id":"7f3a...","answer_kind":"grounded","latency_ms":4210,
       "model_used":"qwen3-8b-q4"}
```

Nhánh câu trả lời ngoài tài liệu (`/ask-external`) dùng cùng hợp đồng nhưng **không bao giờ phát sự kiện `citation`**, và `done.answer_kind` là `external` hoặc `cached_external`.

## 7.2 Luồng tiến độ nạp tài liệu — `GET /notebooks/{id}/sources/events`

| `type` | Payload |
|---|---|
| `source_status` | `{source_id, status, progress, stage_label_key}` |
| `source_ready` | `{source_id, page_count, chunk_count}` |
| `source_failed` | `{source_id, error_code, error_message}` |

`stage_label_key` là **khoá i18n** (`ingest.ocr`, `ingest.indexing`), không phải chuỗi tiếng Việt — frontend tự dịch.

## 7.3 Vòng đời trạng thái nguồn

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> parsing
    parsing --> ocr : cần OCR
    parsing --> chunking : đã có text tốt
    ocr --> chunking
    chunking --> embedding
    embedding --> ready
    parsing --> failed
    ocr --> failed
    chunking --> failed
    embedding --> failed
    failed --> queued : thử lại
    ready --> queued : ép OCR lại / sửa text
    ready --> [*] : xoá
```

**Bất biến vòng đời:** tài liệu **không bao giờ** kẹt ở trạng thái trung gian. Worker khởi động lại phải quét mọi nguồn ở `parsing/ocr/chunking/embedding` cũ hơn timeout và chuyển sang `failed` (US-021 AC-4).

---

# 8. Cấu hình

Toàn bộ tham số ở `settings.py` (đọc từ `.env`). **Không hardcode ở bất kỳ nơi nào khác** — DoD mục D7.

```bash
# ── Ứng dụng ────────────────────────────────────────────────
APP_ENV=dev
SECRET_KEY=                          # BẮT BUỘC đổi khi triển khai
ACCESS_TOKEN_MINUTES=60
REFRESH_TOKEN_DAYS=7
LOGIN_MAX_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15

# ── Hạ tầng ────────────────────────────────────────────────
DATABASE_URL=postgresql+psycopg://documind:documind@postgres:5432/documind
REDIS_URL=redis://redis:6379/0
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=documind

# ── Giới hạn nạp tài liệu ──────────────────────────────────
MAX_FILE_MB=50
MAX_IMAGE_MB=10
MAX_SOURCES_PER_NOTEBOOK=50
ALLOWED_EXTENSIONS=pdf,docx,txt,md,png,jpg,jpeg,webp

# ── Chunking ───────────────────────────────────────────────
CHUNK_TOKENS=768                     # trong khoảng 512–1024 của US-008
CHUNK_OVERLAP_RATIO=0.15             # 10–20%
CHUNK_RESPECT_HEADINGS=true

# ── Phát hiện scan & OCR ───────────────────────────────────
SCAN_CHARS_PER_PAGE_THRESHOLD=100
SCAN_PAGE_RATIO_THRESHOLD=0.5
TEXT_QUALITY_MIN=0.60                # cổng chất lượng tiếng Việt
OCR_ENGINE=paddle
OCR_DPI=300

# ── Mô hình ────────────────────────────────────────────────
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_REVISION=                  # ghim commit hash HuggingFace
EMBEDDING_DIM=1024
EMBEDDING_BATCH_SIZE=16              # điều chỉnh theo VRAM
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_REVISION=
LOCAL_LLM_MODEL=qwen3-8b-q4
GEMINI_API_KEY=                      # để trống → Fast Mode báo hướng dẫn cấu hình
GEMINI_MODEL=gemini-flash

# ── Retrieval (mọi giá trị dưới đây là trục của ablation US-046) ──
RETRIEVAL_VECTOR_ENABLED=true
RETRIEVAL_BM25_ENABLED=true
RETRIEVAL_TOP_N_PER_BRANCH=50
RRF_K=60
RERANK_ENABLED=true
RERANK_TOP_K=8
TAU=0.35                             # trên thang ĐÃ sigmoid; hiệu chỉnh ở US-047
CONTEXTUAL_RETRIEVAL_ENABLED=false   # US-049
VERIFIER_ENABLED=false               # US-063 — tác tử kiểm định, dòng F của ablation
VERIFIER_MAX_RETRY=1
HNSW_EF_SEARCH=120

# ── Định tuyến ý định (US-066) ──────────────────────────────
INTENT_ROUTING_ENABLED=false
INTENT_USE_LLM_FALLBACK=true

# ── Bảo mật ngữ cảnh (US-061) ──────────────────────────────
CONTEXT_DELIMITER=«|CHUNK|»          # bị loại khỏi nội dung chunk trước khi ghép

# ── Hội thoại ──────────────────────────────────────────────
CONDENSE_HISTORY_TURNS=4
LOG_CONDENSED_QUERY=false
DEFAULT_MODE=privacy                 # privacy | fast

# ── Cache câu trả lời ngoài ────────────────────────────────
EXTERNAL_CACHE_SIMILARITY=0.93       # hiệu chỉnh bằng dữ liệu, xem SPEC-REVIEW §B.7
EXTERNAL_CACHE_TTL_DAYS=30
EXTERNAL_CALLS_PER_DAY=50
```

---

# 9. Docker Compose

Sáu service: `postgres` · `redis` · `minio` · `api` · `worker` · `frontend`.

**Bốn điểm bắt buộc:**

1. **`worker` phải thấy GPU** — dùng `deploy.resources.reservations.devices` với `driver: nvidia`, `capabilities: [gpu]`. Trên Windows cần WSL2 + NVIDIA Container Toolkit. Kiểm chứng ở spike S2.
2. **Cache mô hình là volume ngoài** — mount `~/.cache/huggingface` và thư mục model PaddleOCR. Không có nó thì mỗi lần rebuild tải lại ~10 GB.
3. **Init script cho Postgres** — `CREATE EXTENSION vector, citext, unaccent, pgcrypto` và tạo text search config `vi` trước khi Alembic chạy.
4. **Healthcheck + `depends_on: condition: service_healthy`** — `api` không được khởi động trước khi Postgres sẵn sàng.

Dung lượng tải lần đầu (ghi vào README): bge-m3 ~2.2 GB · reranker ~2.2 GB · Qwen3-8B lượng tử ~5–6 GB · PaddleOCR ~100 MB ≈ **10 GB**.

---

# 10. Ngân sách VRAM và hai cấu hình máy

## 10.0 Máy phát triển ≠ máy đích

Dự án chạy trên **hai cấu hình khác nhau**. Mọi mốc hiệu năng trong `SPEC.md` (rerank < 800 ms, OCR < 3 s/trang, token đầu < 8 s ở Privacy Mode) chỉ áp dụng cho **máy đích**, và báo cáo phải ghi rõ cấu hình đã đo.

| | **Máy phát triển** (laptop) | **Máy đích** (server riêng) |
|---|---|---|
| GPU | NVIDIA MX570 — **2 GB VRAM** | **16 GB VRAM** |
| RAM | 15.7 GB | *(ghi lại khi đo lần đầu)* |
| CPU | Intel i5-1240P, 12 nhân | *(ghi lại khi đo lần đầu)* |
| Vai trò | Viết mã, chạy unit test, kiểm thử luồng, dựng giao diện | Index toàn bộ, đo hiệu năng, chạy đánh giá M6, quay video demo |

Ngân sách §10.1 bên dưới áp dụng cho máy đích và **đã đúng** với cấu hình thật.

**Hệ quả kiến trúc:** mọi adapter nặng phải chạy được ở **cả hai chế độ**, chọn bằng config, không phải bằng nhánh mã.

```bash
# .env bổ sung
DEVICE=cpu                    # cpu | cuda — máy phát triển đặt cpu
EMBEDDING_DEVICE=${DEVICE}
RERANK_DEVICE=${DEVICE}
OCR_DEVICE=${DEVICE}
LLM_BACKEND=gemini            # gemini | local — máy phát triển không chạy LLM cục bộ
PERF_ASSERTIONS_ENABLED=false # máy phát triển tắt; máy đích bật
```

**Bốn quy tắc để hai cấu hình không phân kỳ:**

1. **Không hardcode `.cuda()` hay `device="cuda"`** ở bất kỳ đâu — luôn đọc từ config. Đây là một bất biến đáng encode bằng `.agents/skills/encode-invariant`.
2. **AC hiệu năng không chạy trong bộ test thường.** Đánh dấu riêng (`@pytest.mark.perf`) và chỉ chạy trên máy đích. Trên laptop chúng sẽ đỏ mà không có nghĩa gì.
3. **Kết quả đánh giá (M6) chỉ tính khi chạy trên máy đích**, với đúng model đã ghim. Kết quả chạy trên CPU laptop dùng để gỡ lỗi script, không đưa vào báo cáo.
4. **Ghi cấu hình máy vào metadata mỗi lần chạy đánh giá** — tên GPU, VRAM, driver, phiên bản model. Không có nó thì con số không tái lập được.

**Trên laptop 2 GB, thứ gì chạy được:**

| Thành phần | Trên laptop |
|---|---|
| bge-m3 | CPU, chậm ~5–10×. Đủ để kiểm thử luồng với vài chục chunk |
| bge-reranker-v2-m3 | CPU. Bỏ qua mốc 800 ms |
| PaddleOCR | CPU, hoặc GPU nếu chạy một mình |
| LLM | **Chỉ Gemini Flash.** Privacy Mode không kiểm thử được ở đây — chỉ kiểm thử được giao diện chuyển chế độ và đường mã |
| Postgres/Redis/MinIO | Docker, không cần GPU |

## 10.1 Ngân sách trên máy đích

GPU 16 GB (đã xác nhận). Trần toàn hệ thống **15 GB**, chừa 1 GB cho phân mảnh và ngữ cảnh CUDA.

| Thành phần | Ước tính | Chính sách |
|---|---|---|
| LLM cục bộ (Qwen3-8B 4-bit) | ~6–7 GB | Thường trú |
| KV cache | ~1–2 GB | Theo độ dài ngữ cảnh |
| bge-m3 (fp16) | ~2.3 GB | Thường trú khi index, giải phóng được |
| bge-reranker-v2-m3 (fp16) | ~2.3 GB | Thường trú |
| PaddleOCR | ~1 GB | **Nạp theo yêu cầu, giải phóng sau khi xong** |
| **Tổng** | **~13–15 GB** | Sát trần — phải đo thật ở spike S2 |

> 🔴 **Cạm bẫy:** vLLM **tiền cấp phát** theo `gpu_memory_utilization` (mặc định 0.9 → chiếm ~14.4 GB ngay khi khởi động), khiến các mô hình torch khác OOM. Hai lối ra: (a) dùng **Ollama / llama.cpp** cấp phát động; (b) giữ vLLM nhưng đặt `gpu_memory_utilization ≈ 0.45` và nạp/giải phóng embedding + reranker theo yêu cầu. **Quyết định ở spike S2, ghi vào `docs/decisions/`.**

Thêm một **semaphore GPU** ở tầng service: tối đa 1 tác vụ nặng (rerank hoặc sinh) tại một thời điểm, để hai truy vấn đồng thời không tranh chấp.

---

# 11. Ma trận truy vết — User Story → mục kỹ thuật

Thay thế cột "FR (SPEC v1.0)" ở mục J.4 của `SPEC.md`.

| User Story | Mục trong tài liệu này |
|---|---|
| US-001 | §2 · §9 |
| US-002 → US-004 | §4.2 (`users`, `refresh_tokens`) · §6.2 |
| US-005, US-020 | §4.2 (`notebooks`, `sources`) · §6.3 · §6.4 · INV-4 |
| US-006, US-025 | §6.4 |
| US-007 | §1.2 luồng A · §4.2 (`source_texts`) · INV-2 |
| US-008 | §4.2 (`source_chunks`) · INV-1 |
| US-009 | §4.2 chỉ mục HNSW/GIN · §5.2 |
| US-010 | §5.1 · §5.2 · §5.3 |
| US-011, US-031 | §5.4 |
| US-012, US-013 | §7.1 · §4.2 (`chat_messages.answer_kind`) |
| US-014, US-015 | §4.2 (`message_citations`) · §7.1 sự kiện `citation` · §6.5 `/citations/{id}` |
| US-016, US-017 | §6.4 `/sources/{id}/file` |
| US-018, US-019 | §4.2 (`chat_sessions`, `condensed_query`) · §6.5 |
| US-021 → US-023 | §7.2 · §7.3 · §8 |
| US-024, US-026 | §3.2 `OCRProvider` · §8 |
| US-027 | §6.4 `PATCH /sources/{id}/text` |
| US-029, US-030 | §3.2 `LLMProvider` · §10 |
| US-032 → US-035 | §4.2 (`external_answer_cache`, `external_call_log`) · INV-3 · §6.6 |
| US-036, US-037 | §4.2 (`users.locale`, `error_code`) · §7.2 `stage_label_key` |
| US-038 | §4.2 (`chat_sessions.scope_source_ids`) · §5.1 · §5.2 |
| US-039 | §4.2 (`share_links`) · §6.6 |
| US-040, US-041 | §6.5 · §6.6 |
| US-044 → US-048 | §3.3 thư mục `eval/` · §8 (các cờ ablation) |
| US-049 | §4.2 (`context_prefix`) · §8 |

---

# 12. Thứ tự xây dựng ở M1

Trình tự đi từ trong ra ngoài, mỗi bước kiểm chứng được ngay:

1. `docker compose up` với 3 service hạ tầng → `make migrate` chạy sạch → có bảng và extension.
2. `app/text/normalize.py` + `segment.py` + test → **INV-2 xanh trước khi làm gì khác**.
3. Trích xuất PDF → `source_texts` → test đọc lại đúng tiếng Việt có dấu.
4. Chunker → `source_chunks` → **`test_offset_roundtrip` xanh (INV-1)**.
5. Embedding + ghi vector + tạo `tsv` → kiểm tra chỉ mục HNSW và GIN tồn tại.
6. Xác thực + notebook + upload → nối vào Celery.
7. `GET /health` xanh, `docker compose up -d` một lệnh chạy hết → **cổng ra GĐ 0**.

> Bước 2 và 4 là hai chốt chặn. Nếu chúng chưa xanh, đừng đi tiếp — mọi thứ phía sau đều đứng trên chúng.
