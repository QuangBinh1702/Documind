# DocuMind

Hỏi đáp trên tài liệu của chính bạn, **luôn kèm trích dẫn kiểm chứng được** —
mỗi khẳng định trong câu trả lời gắn một số, bấm vào số đó là mở đúng đoạn văn
gốc, đúng trang, đúng vùng trên trang.

Chạy được hoàn toàn trên máy của bạn: tài liệu không rời khỏi máy trừ khi bạn
chủ động chọn như vậy.

> Đồ án tốt nghiệp. Đặc tả đầy đủ ở [`SPEC.md`](SPEC.md), quyết định kỹ thuật ở
> [`docs/decisions/`](docs/decisions/), số liệu đo thật ở
> [`docs/evidence/`](docs/evidence/).

---

## Hệ thống làm được gì

| | |
|---|---|
| **Nạp tài liệu** | PDF (có lớp text hoặc bản scan), DOCX, TXT, Markdown, ảnh (PNG/JPG/WebP, kể cả dán từ clipboard) |
| **Bản scan và ảnh** | Nhận dạng chữ bằng PP-OCRv5, giữ toạ độ nên vẫn trích dẫn tới đúng vùng trên trang |
| **Truy xuất** | Lai ghép: vector ngữ nghĩa (pgvector) + từ khoá tiếng Việt (Postgres FTS), hợp nhất bằng RRF, xếp hạng lại bằng cross-encoder |
| **Chống bịa** | Cổng ngưỡng τ đứng **trước** lượt gọi mô hình; không đủ căn cứ thì từ chối chứ không đoán |
| **Trích dẫn** | Marker `[n]` → chunk → trang → vùng toạ độ; marker mô hình bịa ra bị loại trước khi hiển thị |
| **Quyền riêng tư** | Privacy Mode chạy mô hình cục bộ, không có gì rời khỏi máy. Fast Mode gọi dịch vụ ngoài và **nói rõ điều đó** |
| **Chia sẻ** | Liên kết chỉ đọc: người nhận xem và hỏi được, không sửa hay xoá được gì |
| **Xuất** | Hội thoại ra Markdown hoặc PDF, kèm danh mục trích dẫn |
| **Giao diện** | Tiếng Việt và tiếng Anh, chế độ sáng/tối, ba cột kéo được |

---

## Yêu cầu hệ thống

**Bắt buộc**

- Docker và Docker Compose (bản v2, tức lệnh `docker compose`, không phải
  `docker-compose`)
- 8 GB RAM trở lên
- **~16 GB đĩa trống**, đo thật chứ không ước lượng:

  | | |
  |---|---|
  | Ảnh Docker (`api`, `worker`, `frontend`) | 8,0 GB |
  | Trọng số mô hình (volume `model-cache`) | 6,4 GB |
  | Postgres, MinIO, Redis và tài liệu của bạn | phần còn lại |

  `api` và `worker` dùng chung một ảnh 3,2 GB nên chỉ tính một lần.

**Tuỳ chọn nhưng nên có**

- GPU NVIDIA ≥ 12 GB VRAM kèm NVIDIA Container Toolkit, nếu muốn chạy mô hình
  ngôn ngữ cục bộ. Không có GPU thì hệ thống vẫn chạy đầy đủ ở chế độ CPU —
  chỉ chậm hơn, và mô hình ngôn ngữ khi đó nên dùng Fast Mode.

Hệ thống đã chạy trên Windows 11 (Docker Desktop) và Linux. Trên macOS Apple
Silicon thì Docker không truy cập được GPU, nên chạy ở chế độ CPU.

---

## Chạy trong 5 phút

```bash
git clone <url-repo> documind
cd documind

cp .env.example .env
# Sinh khoá bí mật rồi dán vào SECRET_KEY trong .env:
python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up -d
```

Chờ khoảng một phút cho Postgres và MinIO sẵn sàng, rồi mở:

| | |
|---|---|
| Giao diện | <http://localhost:3000> |
| Tài liệu API | <http://localhost:8000/api/docs> |
| MinIO Console | <http://localhost:9001> (minioadmin / minioadmin) |

Đăng ký một tài khoản ngay trên trang chủ, tạo notebook, kéo một tệp PDF vào,
đợi trạng thái chuyển sang **sẵn sàng**, rồi hỏi.

> **Lần dựng đầu mất khoảng 10–15 phút** và tải về vài GB (PyTorch, thư viện
> Node). Những lần sau dùng cache nên chỉ vài giây.
>
> **Tài liệu đầu tiên cũng lâu**, và nó tải làm **hai đợt** — biết trước thì đỡ
> tưởng là treo:
>
> | Khi nào | Tải gì | Dung lượng |
> |---|---|---|
> | Tải tài liệu đầu tiên | `bge-m3` (nhúng) | 4,3 GB |
> | Đặt **câu hỏi** đầu tiên | `bge-reranker-v2-m3` (xếp hạng lại) | 2,1 GB |
> | | **Tổng trong volume `model-cache`** | **6,4 GB** |
>
> Đo trên máy phát triển: đợt một mất khoảng 3 phút, sau đó một tệp DOCX 10
> nghìn ký tự xử lý xong trong 47 giây. Từ tài liệu và câu hỏi thứ hai trở đi
> không phải tải nữa.
>
> Theo dõi bằng `docker compose logs -f worker`.

Ảnh dựng ra: `documind-api` và `documind-worker` mỗi cái 3,2 GB,
`documind-frontend` 1,6 GB. Ảnh backend cài **PyTorch bản chỉ CPU** — bản CUDA
mặc định của PyPI nặng hơn 2,5 GB và vô dụng khi `DEVICE=cpu`. Máy có GPU thì
dựng lại bằng:

```bash
docker compose build --build-arg TORCH_INDEX=https://pypi.org/simple api worker
```

---

## Tải mô hình trước (khuyến nghị)

Tải sẵn trước khi dùng thì tài liệu đầu tiên không phải chờ:

```bash
docker compose exec worker python -c "
from sentence_transformers import SentenceTransformer, CrossEncoder
SentenceTransformer('BAAI/bge-m3')
CrossEncoder('BAAI/bge-reranker-v2-m3')
print('Xong — trọng số đã nằm trong volume model-cache')
"
```

Mô hình OCR (PP-OCRv5, vài chục MB) tự tải ở lần OCR đầu tiên.

**Mô hình ngôn ngữ cục bộ** (Privacy Mode) chạy bằng Ollama ở ngoài Docker:

```bash
ollama pull qwen3:8b
ollama serve
```

rồi đặt trong `.env`:

```ini
DEFAULT_MODE=privacy
LOCAL_LLM_MODEL=qwen3:8b
LOCAL_LLM_BASE_URL=http://host.docker.internal:11434/v1
```

Không có GPU đủ mạnh thì dùng Fast Mode: điền `GEMINI_API_KEY` hoặc
`OLLAMA_CLOUD_API_KEY`, đặt `DEFAULT_MODE=fast`. Giao diện sẽ hiện nhãn cho biết
dữ liệu rời khỏi máy.

---

## Biến môi trường

Mọi tham số của hệ thống nằm ở `.env`; không có giá trị nào bị hardcode ở nơi
khác. `.env.example` liệt kê đủ và kèm giá trị mặc định an toàn — **nó không
chứa khoá API thật**, và `.env` nằm trong `.gitignore`.

### Ứng dụng và bảo mật

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `APP_ENV` | `dev` | `dev` hoặc `production`. `production` đóng các đường chỉ dành cho phát triển |
| `LOG_LEVEL` | `INFO` | Mức ghi nhật ký |
| `SECRET_KEY` | *(phải đổi)* | Khoá ký JWT. **Bắt buộc đổi trước khi triển khai** |
| `ACCESS_TOKEN_MINUTES` | `60` | Tuổi thọ access token |
| `REFRESH_TOKEN_DAYS` | `7` | Tuổi thọ refresh token |
| `LOGIN_MAX_ATTEMPTS` | `5` | Số lần sai trước khi khoá |
| `LOGIN_LOCKOUT_MINUTES` | `15` | Thời gian khoá |
| `LOGIN_WINDOW_MINUTES` | `5` | Cửa sổ đếm số lần sai |

### Thiết bị tính toán

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DEVICE` | `cpu` | `cpu` hoặc `cuda`. Máy đích có GPU thì đặt `cuda` |
| `EMBEDDING_DEVICE` · `RERANK_DEVICE` · `OCR_DEVICE` | *(trống)* | Bỏ trống = kế thừa `DEVICE`. Chỉ điền khi muốn tách riêng |
| `PERF_ASSERTIONS_ENABLED` | `false` | Bật mốc hiệu năng. **Chỉ bật trên máy đích** — trên laptop chúng đỏ mà không mang ý nghĩa |

### Hạ tầng

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `POSTGRES_USER` / `_PASSWORD` / `_DB` / `_PORT` | `documind` / `documind` / `documind` / `5432` | Cơ sở dữ liệu |
| `REDIS_PORT` | `6379` | Redis — hàng đợi Celery, tiến độ xử lý, bộ đếm đăng nhập |
| `MINIO_ROOT_USER` / `_PASSWORD` | `minioadmin` | **Đổi trước khi triển khai** |
| `MINIO_BUCKET` / `_PORT` / `_CONSOLE_PORT` / `_SECURE` | `documind` / `9000` / `9001` / `false` | Lưu trữ tệp gốc |
| `API_PORT` / `FRONTEND_PORT` | `8000` / `3000` | Cổng phơi ra ngoài |
| `DATABASE_URL` · `REDIS_URL` · `MINIO_ENDPOINT` | *(trống)* | Chỉ điền khi chạy backend **ngoài** Docker |

### Nạp tài liệu

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `MAX_FILE_MB` | `50` | Hạn mức mỗi tệp |
| `MAX_IMAGE_MB` | `10` | Hạn mức riêng cho ảnh — ảnh lớn hơn chỉ làm OCR chậm chứ không đọc ra nhiều chữ hơn |
| `MAX_SOURCES_PER_NOTEBOOK` | `50` | Số nguồn tối đa mỗi notebook |
| `ALLOWED_EXTENSIONS` | `pdf,docx,txt,md,png,jpg,jpeg,webp` | Định dạng nhận |
| `CHUNK_TOKENS` | `768` | Kích thước đoạn |
| `CHUNK_OVERLAP_RATIO` | `0.15` | Tỉ lệ chồng lấn giữa hai đoạn liền kề |
| `CHUNK_RESPECT_HEADINGS` | `true` | Cắt theo ranh giới tiêu đề khi có thể |
| `WORKER_MODE` | `celery` | `celery` = worker riêng (đúng). `inline` = chạy trong tiến trình API, chỉ dùng khi phát triển |
| `TASK_TIME_LIMIT_SECONDS` | `3600` | Trần cứng cho một lượt nạp |

### Phát hiện scan, OCR và cổng chất lượng

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `SCAN_CHARS_PER_PAGE_THRESHOLD` | `100` | Dưới ngần này ký tự thì trang coi như không có lớp văn bản |
| `SCAN_PAGE_RATIO_THRESHOLD` | `0.5` | Tỉ lệ trang như vậy để kết luận cả tệp là bản scan |
| `TEXT_QUALITY_MIN` | `0.60` | Ngưỡng cổng chất lượng US-056 |
| `OCR_ENABLED` | `true` | Tắt thì bản scan bị từ chối kèm lý do rõ ràng |
| `OCR_ENGINE` | `rapid` | `rapid` (ONNX Runtime) hoặc `paddle`. Xem *Khắc phục sự cố* |
| `OCR_REC_LANG` | `latin` | **Đừng để `ch`** — nó đọc tiếng Việt mất sạch dấu mà vẫn tự báo tin cậy 0.98 |
| `OCR_DPI` | `300` | Độ phân giải render trang trước khi nhận dạng |
| `OCR_MIN_CONFIDENCE` | `0.60` | Dưới ngưỡng thì đếm để cảnh báo, không tự ý bỏ dòng |
| `IMAGE_MIN_SIDE` / `IMAGE_MAX_SIDE` | `1600` / `3200` | Cỡ ảnh đưa vào OCR |

### Mô hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `EMBEDDING_PROVIDER` | `bge-m3` | `bge-m3`, `tei` hoặc `fake`. `fake` là adapter tất định để chạy test — **không dùng cho số liệu báo cáo** |
| `EMBEDDING_MODEL` / `_REVISION` / `_DIM` / `_BATCH_SIZE` | `BAAI/bge-m3` / *(trống)* / `1024` / `16` | Ghim revision để kết quả tái lập được |
| `RERANK_PROVIDER` / `_MODEL` / `_REVISION` | `bge` / `BAAI/bge-reranker-v2-m3` / *(trống)* | `bge`, `tei` hoặc `fake`. Cross-encoder xếp hạng lại |
| `TEI_BASE_URL` / `TEI_API_KEY` | `https://textembedding.dutai.io.vn` / *(trống)* | Chỉ dùng khi chọn `tei`. Gốc tên miền, **không** kèm `/v1` |
| `TEI_TIMEOUT_SECONDS` / `TEI_MAX_BATCH` | `90` / `4` | Adapter tự chia lô. **Đừng để `32`** như tài liệu dịch vụ khuyến nghị — xem đo thật bên dưới |
| `LLM_PROVIDER` | `real` | `real` hoặc `fake` |
| `DEFAULT_MODE` | `privacy` | `privacy` = không gì rời khỏi máy. `fast` = gọi dịch vụ ngoài |
| `FAST_BACKEND` | `gemini` | `gemini` hoặc `ollama-cloud` |
| `LOCAL_LLM_MODEL` / `_BASE_URL` | `qwen3:8b` / `http://host.docker.internal:11434/v1` | Máy chủ tương thích OpenAI chạy cục bộ (Ollama trên máy chủ; hoặc `http://ollama:11434/v1` với profile `local-llm`). **Đừng trỏ sang đám mây** — cờ `is_local` khi đó nói dối và giao diện không cảnh báo |
| `LLM_CONTEXT_TOKENS` / `LLM_CHARS_PER_TOKEN` | `8192` / `2.0` | Cửa sổ ngữ cảnh mà prompt phải vừa; đoạn xếp hạng thấp bị bỏ bớt cho vừa. Đặt `OLLAMA_CONTEXT_LENGTH` của máy chủ mô hình bằng con số này |
| `CORS_ORIGINS` | `http://localhost:3000,…` | Origin của giao diện được gọi API. Qua Caddy cùng origin thì không cần |
| `SHARE_ASKS_PER_HOUR` / `REGISTER_PER_HOUR_PER_IP` | `30` / `10` | Trần cho endpoint không đăng nhập. `0` = tắt |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | *(trống)* / `gemini-3.1-flash-lite` | Ghim phiên bản cụ thể, đừng dùng bí danh `-latest` |
| `OLLAMA_CLOUD_API_KEY` / `_MODEL` / `_BASE_URL` | *(trống)* / `gemma4:31b` / `https://ollama.com/v1` | Trọng số mở nhưng chạy trên máy của Ollama — dữ liệu **vẫn** rời khỏi máy |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | `0.0` / `1024` | `0.0` để câu trả lời bám tài liệu và để chạy lại đánh giá ra cùng kết quả |
| `PDF_FONT` | *(trống)* | Font Unicode khi xuất PDF. Bỏ trống = tự dò |

#### Chạy nhúng và rerank qua dịch vụ TEI

Máy chủ Text Embeddings Inference của khoa phục vụ **đúng hai mô hình mà đồ án
đang chạy cục bộ** — `BAAI/bge-m3` và `BAAI/bge-reranker-v2-m3`. Chọn `tei` là
đổi *chỗ chạy*, không phải đổi mô hình: vẫn 1024 chiều, không phải lập chỉ mục
lại, `TAU` và ngưỡng cache vẫn giữ nguyên hiệu lực.

```ini
EMBEDDING_PROVIDER=tei
RERANK_PROVIDER=tei
TEI_API_KEY=<khoá của bạn>
```

Nó đáng dùng nhất trên laptop CPU: cross-encoder chạy tuyến tính theo số ứng
viên, nên `RERANK_CANDIDATES=50` ở đây biến mỗi câu hỏi thành hàng phút, còn
qua TEI thì đó là một lượt gọi trên GPU.

**Kích thước lô: đừng theo con số 32 trong tài liệu dịch vụ.** Con số đó dành
cho câu ngắn; đoạn của đồ án dài 768 token. Đo thật ngày 26/08/2026 với đoạn
~1300 token:

| Lô | Thời gian | Mỗi đoạn |
|---|---|---|
| 1 | 3,8 s | 3,8 s |
| 2 | 6,5 s | 3,3 s |
| 4 | 13,5 s | 3,4 s |
| 16 | 58,6 s | 3,7 s |

Dịch vụ xử lý **tuần tự**: gộp lô không nhanh hơn chút nào, chỉ đổi lấy rủi ro
hết giờ. Để `TEI_MAX_BATCH=32` thì lượt nạp tài liệu đầu tiên chết ở `/embed`
sau hai lần thử lại. Mặc định `4` là mức vừa với `TEI_TIMEOUT_SECONDS=90`.

Hệ quả cần biết: một tài liệu 23 đoạn mất khoảng 5 phút để nạp. Nhanh hơn nhiều
so với chạy bge-m3 trên CPU, nhưng **không** phải tốc độ GPU — dịch vụ dùng
chung nên có xếp hàng.

> **Đánh đổi, và nó lớn.** Nhúng và xếp hạng lại chạy ở **mọi** lượt hỏi và
> **mọi** lượt nạp tài liệu, không phân biệt chế độ. Bật `tei` nghĩa là nội
> dung tài liệu và câu hỏi rời khỏi máy **kể cả ở Privacy Mode**, nên dòng
> "không có gì rời khỏi máy" ở bảng trên không còn đúng. `/api/health` phát
> cảnh báo tương ứng. Dùng cho phát triển; số liệu trong báo cáo nên chạy bằng
> mô hình cục bộ có ghim revision (US-045 AC-5) — dịch vụ ngoài không ghim
> được phiên bản trọng số.

### Truy xuất — mỗi biến ở đây là một trục của bảng ablation

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RETRIEVAL_VECTOR_ENABLED` / `_BM25_ENABLED` | `true` / `true` | Bật tắt từng nhánh truy xuất |
| `RETRIEVAL_TOP_N_PER_BRANCH` | `50` | Số ứng viên mỗi nhánh trả về |
| `RRF_K` | `60` | Hằng số của Reciprocal Rank Fusion |
| `RERANK_ENABLED` | `true` | Bật cross-encoder |
| `RERANK_CANDIDATES` | `50` | Chấm bao nhiêu đoạn — chi phối **độ trễ**. Trên CPU hạ xuống 10–20 thay vì tắt hẳn rerank |
| `RERANK_TOP_K` | `8` | Giữ bao nhiêu đoạn làm ngữ cảnh — chi phối **câu trả lời** |
| `TAU` | `0.35` | Ngưỡng "đủ căn cứ", trên thang đã sigmoid |
| `CONTEXTUAL_RETRIEVAL_ENABLED` | `false` | Sinh câu bối cảnh cho mỗi đoạn trước khi nhúng |
| `VERIFIER_ENABLED` / `VERIFIER_MAX_RETRY` | `false` / `1` | Kiểm định câu trả lời và sinh lại nếu có khẳng định không được chứng thực |
| `HNSW_EF_SEARCH` | `120` | Tham số tìm kiếm của chỉ mục vector |
| `INTENT_ROUTING_ENABLED` / `INTENT_USE_LLM_FALLBACK` | `false` / `true` | Định tuyến "bạn là ai?" ra khỏi đường truy xuất |
| `CONTEXT_DELIMITER` | `«\|CHUNK\|»` | Ranh giới bọc nội dung tài liệu, chống prompt injection |
| `CONDENSE_HISTORY_TURNS` | `4` | Số lượt gần nhất dùng để gộp câu hỏi phụ thuộc ngữ cảnh |
| `LOG_CONDENSED_QUERY` | `false` | Ghi câu hỏi đã gộp vào log — chứa nội dung người dùng, nên mặc định tắt |
| `EXTERNAL_CACHE_SIMILARITY` | `0.93` | Ngưỡng dùng lại câu trả lời ngoài đã lưu |
| `EXTERNAL_CACHE_TTL_DAYS` / `EXTERNAL_CALLS_PER_DAY` | `30` / `50` | Hạn dùng và hạn mức gọi ra ngoài mỗi ngày |

---

## Kiến trúc

Sơ đồ đầy đủ ở [`docs/diagrams/`](docs/diagrams/) — viết bằng Mermaid, GitHub
dựng hình trực tiếp khi mở xem.

```
                    ┌──────────────┐
   Trình duyệt ────►│   frontend   │  Next.js 15 · React 19 · Tailwind 4
        │           └──────────────┘
        │  gọi thẳng, không qua proxy (proxy đệm mất streaming SSE)
        ▼
   ┌──────────┐        ┌────────────┐
   │   api    │───────►│   worker   │  Celery, concurrency=1 — GPU gắn ở đây
   └────┬─────┘ Redis  └─────┬──────┘
        │                    │
        ▼                    ▼
   ┌─────────────────────────────────┐
   │  PostgreSQL 17 + pgvector       │  chunk · vector · tsvector · hội thoại
   │  MinIO                          │  tệp gốc
   │  Redis                          │  hàng đợi · tiến độ · chặn dò mật khẩu
   └─────────────────────────────────┘
```

Backend theo **ports & adapters**: mỗi mô hình đứng sau một cổng
(`EmbeddingProvider`, `RerankProvider`, `LLMProvider`, `OcrProvider`), và mỗi
cổng có ít nhất một adapter thật cùng một adapter giả tất định. Nhờ vậy bộ test
chạy được trên máy không GPU, và bảng ablation đổi được từng tầng bằng một dòng
cấu hình.

### Bốn bất biến

Đây là những tính chất mà phần lớn mã tồn tại để bảo vệ. Vi phạm chúng không làm
gì đổ vỡ ngay — hệ thống chỉ dần trả lời sai.

| | |
|---|---|
| **INV-1** | Cắt `full_text[char_start:char_end]` phải ra đúng nội dung chunk. Đây là thứ khiến trích dẫn trỏ đúng chỗ, và nó được kiểm trên **dữ liệu đã ghi vào cơ sở dữ liệu**, không phải trên đối tượng trong bộ nhớ |
| **INV-2** | Mọi văn bản ở dạng chuẩn Unicode NFC trước khi tính offset |
| **INV-3** | Đường truy xuất tài liệu **không bao giờ** đọc `external_answer_cache`. Trộn hai thứ vào nhau thì hệ thống sẽ trích dẫn chính những nội dung nó tự sinh ra |
| **INV-4** | Mọi truy vấn dữ liệu người dùng lọc theo `user_id` ngay ở tầng SQL |

---

## Phát triển

### Chạy backend ngoài Docker

```bash
docker compose up -d postgres redis minio minio-init

cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS
pip install -e ".[dev,ml]"    # bỏ ",ml" nếu chỉ chạy test với adapter giả
# ".[ml,paddle]" nếu cần thêm PaddleOCR cho US-048 — xem Khắc phục sự cố

# Bỏ comment ba dòng DATABASE_URL / REDIS_URL / MINIO_ENDPOINT trong .env
# và đặt WORKER_MODE=inline (không có worker container).

alembic upgrade head
uvicorn app.main:app --reload
```

### Chạy test

```bash
cd backend
pytest                    # cần postgres, redis, minio đang chạy
pytest -m "not db"        # chỉ test không cần hạ tầng
ruff check app tests
```

Bộ test dùng adapter giả nên không cần GPU và không gọi mạng — `conftest.py`
chặn thẳng tầng kết nối, vì một test viết ra để kiểm ca "thiếu khoá API" đã từng
thật sự gọi tới Google.

### Chạy frontend ngoài Docker

```bash
cd frontend
npm install
npm run dev
```

### Đánh giá chất lượng

```bash
cd eval
python run_eval.py          # RAGAS trên bộ câu hỏi có nhãn
python ablation.py          # bảng so cấu hình
python tau_sweep.py         # hiệu chỉnh ngưỡng τ
python do_dong_thoi.py      # đo tải đồng thời
python hieu_chinh_cache.py  # hiệu chỉnh ngưỡng cache
```

Xem [`eval/README.md`](eval/README.md).

---

## Khắc phục sự cố

**Tài liệu kẹt mãi ở "đang chờ"**
`WORKER_MODE` không khớp với cách đang chạy. Đi bằng Docker thì phải là `celery`
(có container `worker`); chạy backend trần không bật worker thì phải là
`inline`. Kiểm tra thêm bằng `docker compose logs worker`.

**Tài liệu đầu tiên rất lâu**
Lần đầu phải tải ~10 GB trọng số. Theo dõi bằng
`docker compose logs -f worker`, hoặc tải trước theo mục *Tải mô hình trước*.

**`OCR_ENGINE=paddle` báo `ValueError: Type of attribute: strides is not right`**
PaddlePaddle 3.0.0 không nạp được chính mô hình mà PaddleOCR tải về. Dùng
`OCR_ENGINE=rapid` — cùng họ mô hình PP-OCRv5, chạy qua ONNX Runtime. Vì lý do
này `paddleocr` nằm ở nhóm phụ thuộc **riêng** (`.[paddle]`), không nằm trong
`.[ml]`: ảnh Docker không nên mang theo một gigabyte phụ thuộc đang hỏng.

**Chữ tiếng Việt trong bản scan mất sạch dấu**
`OCR_REC_LANG` đang để `ch`. Đổi sang `latin`. Chi tiết và số đo ở
[`docs/evidence/M3-ocr-tieng-viet.md`](docs/evidence/M3-ocr-tieng-viet.md).

**Câu trả lời hiện ra một cục ở cuối thay vì chạy dần**
Có proxy đứng giữa và nó đệm luồng SSE. Trình duyệt phải gọi thẳng API; đó là lý
do `next.config.ts` cố ý **không** cấu hình `rewrites`.

**Xuất PDF ra ô vuông thay vì chữ tiếng Việt**
Máy chủ không có font Unicode nào. Ảnh Docker đã cài `fonts-dejavu-core`; chạy
ngoài Docker thì cài một font hoặc trỏ `PDF_FONT` tới một tệp `.ttf`.

**`docker compose up` báo cổng đã bị chiếm**
Đổi `POSTGRES_PORT`, `API_PORT`, `FRONTEND_PORT`… trong `.env`.

**Container thoát ngay sau khi Docker Desktop khởi động lại**
Container thoát với mã 0 khi Docker tắt, và `restart: unless-stopped` không hồi
sinh chúng. Chạy lại `docker compose up -d`.

**Đổi tệp `infra/postgres/init/` mà không thấy tác dụng**
Script khởi tạo chỉ chạy khi volume còn rỗng. Xoá volume:
`docker compose down -v` (**mất toàn bộ dữ liệu**).

---

## Cấu trúc thư mục

```
backend/          FastAPI, dịch vụ, adapter, worker, migration Alembic
  app/api/        tầng HTTP — chỉ điều phối, không chứa nghiệp vụ
  app/services/   nghiệp vụ
  app/ports/      giao thức cho mô hình
  app/adapters/   cài đặt cụ thể, mỗi cổng có bản thật và bản giả
  app/models/     ánh xạ SQLAlchemy
  tests/          bộ test
frontend/         Next.js 15 App Router
eval/             bộ đánh giá định lượng
docs/             quyết định kỹ thuật, bằng chứng đo, sơ đồ
infra/            script khởi tạo Postgres
spikes/           thử nghiệm rủi ro kỹ thuật ở giai đoạn đầu
```

---

## Giấy phép và ghi công

Đồ án học thuật. Mô hình sử dụng: **BAAI/bge-m3**, **BAAI/bge-reranker-v2-m3**
(MIT), **PP-OCRv5** qua RapidOCR (Apache-2.0).
