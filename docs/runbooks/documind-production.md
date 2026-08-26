# Application Runbook: DocuMind trên một máy chủ Linux

Theo mẫu `docs/templates/application-runbook.md`. Mọi lệnh ở đây đã được chạy
thật trên bản dev; phần nào chưa kiểm chứng trên máy đích ghi ở **Unknowns**.

## Scope

Toàn bộ hệ thống DocuMind — giao diện Next.js, API FastAPI, worker Celery,
Postgres/pgvector, Redis, MinIO, Caddy và (tuỳ chọn) Ollama — chạy bằng Docker
Compose trên **một** máy chủ Linux, phục vụ người dùng thật qua HTTPS.

## Prerequisites

- Ubuntu 22.04/24.04, Docker Engine ≥ 24 và `docker compose` v2.24+ (lớp phủ
  dùng thẻ `!reset`).
- Một tên miền trỏ A record về máy chủ; cổng 80 và 443 mở. Không có tên miền
  thì `DOMAIN=localhost` để Caddy tự ký chứng chỉ (trình duyệt cảnh báo).
- Máy có GPU: NVIDIA driver + `nvidia-container-toolkit`, và
  `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`
  phải in ra card.
- Đĩa: ~16 GB cho ảnh và trọng số (README) cộng thêm ~5 GB cho `qwen3:8b`.
- Tường lửa: chỉ 22/80/443. Postgres, Redis, MinIO **không** phơi ra ngoài ở
  bản prod.

## Start

```bash
git clone <repo> /opt/documind && cd /opt/documind
cp .env.example .env
# Ghi đè bằng các dòng trong .env.production.example — đặc biệt SECRET_KEY,
# POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD, REDIS_PASSWORD, DOMAIN.
$EDITOR .env

# Máy không GPU
docker compose -f docker-compose.yml -f compose.prod.yml up -d --build

# Máy có GPU, chạy Ollama trong compose
docker compose -f docker-compose.yml -f compose.prod.yml -f compose.gpu.yml \
    --profile local-llm up -d --build
docker compose -f docker-compose.yml -f compose.prod.yml exec ollama ollama pull qwen3:8b
```

Cổng phơi ra máy chủ: chỉ `80`, `443` (Caddy). Trạng thái ghi ở các volume
`documind_postgres-data`, `documind_minio-data`, `documind_redis-data`,
`documind_model-cache`, `documind_ollama-models`, `documind_caddy-data`.

Giá trị **cố định**: đường `/api/*` → api:8000, còn lại → frontend:3000.
**Mặc định nhưng đổi được**: trần bộ nhớ (`*_MEMORY_LIMIT`), `MAX_FILE_MB`.
**Bắt buộc đặt**: `DOMAIN` và bốn bí mật — thiếu là compose từ chối chạy, và
API từ chối khởi động nếu bí mật còn là giá trị mẫu (`app/settings.py::loi_chan_khoi_dong`).

## Readiness

```bash
docker compose -f docker-compose.yml -f compose.prod.yml ps   # mọi service (healthy)
curl -fsS https://$DOMAIN/api/health                            # {"status":"ok",...}
```

Ở production `/api/health` chỉ trả trạng thái từng thành phần, không trả chi
tiết lỗi hay cảnh báo cấu hình — xem log để biết lý do khi `degraded`.

Lần đầu, worker tải `bge-m3` (4,3 GB) ở tài liệu đầu tiên và API tải reranker
(2,1 GB) ở câu hỏi đầu tiên. Tải trước để người dùng đầu tiên không phải chờ:

```bash
docker compose -f docker-compose.yml -f compose.prod.yml exec worker python -c "
from sentence_transformers import SentenceTransformer, CrossEncoder
SentenceTransformer('BAAI/bge-m3'); CrossEncoder('BAAI/bge-reranker-v2-m3')"
```

## Deterministic State

- Xoá sạch dữ liệu (không xoá trọng số): `docker compose ... down` rồi
  `docker volume rm documind_postgres-data documind_minio-data documind_redis-data`.
- Khôi phục từ bản sao lưu: `./infra/backup/restore.sh <pg.dump> <minio.tar.gz>`.
- Tài khoản demo: đăng ký qua giao diện; `REGISTER_PER_HOUR_PER_IP` (mặc định
  10) giới hạn số tài khoản tạo từ một địa chỉ.

## Interface

- Giao diện: `https://$DOMAIN/`. API docs: `https://$DOMAIN/api/docs`.
- Liên kết chia sẻ: `https://$DOMAIN/xem/<token>` — không cần đăng nhập, bị
  giới hạn `SHARE_ASKS_PER_HOUR` câu hỏi mỗi giờ cho mỗi liên kết.
- CLI nạp tài liệu hàng loạt: `docker compose ... exec worker python -m app.cli --help`.

## Runtime Evidence

```bash
C="docker compose -f docker-compose.yml -f compose.prod.yml"
$C logs -f --tail=200 api        # request, cảnh báo cấu hình lúc khởi động
$C logs -f --tail=200 worker     # từng bước nạp tài liệu, thời gian nhúng
$C logs -f --tail=200 caddy      # access log JSON: đường dẫn, mã, độ trễ
$C exec redis redis-cli -a "$REDIS_PASSWORD" keys 'documind:*'   # tiến độ, khoá đăng nhập, rate limit
```

Log xoay vòng 5 × 20 MB mỗi container (`x-logging` trong `compose.prod.yml`).
Trường bảo đảm trong log API: thời điểm, mức, tên logger, thông điệp. Không
có request-id tương quan (xem Unknowns).

## Ownership And Cleanup

Mọi container tên `documind-*`, mọi volume tên `documind_*`, network
`documind_default`. `docker compose ... down` dừng và xoá container, giữ
volume; thêm `-v` để xoá cả dữ liệu.

Sao lưu hằng ngày bằng cron: `./infra/backup/backup.sh /var/backups/documind`
(Postgres `pg_dump -Fc` + tar volume MinIO, giữ 14 bản). Trọng số mô hình
không sao lưu — tải lại được.

## Validation

- Bộ test backend (cần hạ tầng dev): `cd backend && pytest -m "not perf and not ml"`
  — 581 test xanh ở thời điểm viết.
- Giao diện: `cd frontend && npm run typecheck && npm run lint && npm run build`.
- Hành trình thật: đăng ký → tạo notebook → tải một PDF → đợi *sẵn sàng* →
  hỏi → bấm số trích dẫn thấy đúng đoạn được tô sáng → xuất PDF → tạo liên
  kết chia sẻ và mở ở cửa sổ ẩn danh.
- Mốc hiệu năng trên máy đích: `pytest -m perf` với `PERF_ASSERTIONS_ENABLED=true`.

## Unknowns

- **Chưa chạy trên máy đích 16 GB.** Ngân sách VRAM ở `SPEC-v1.md §10.1` là
  ước tính; spike S2 (`spikes/s2_vram.py`) chưa được chạy. Nếu tổng
  qwen3:8b + bge-m3 + reranker + OCR vượt 16 GB thì phương án là chạy
  embedding/reranker trên CPU (`EMBEDDING_DEVICE=cpu`, `RERANK_DEVICE=cpu`).
- Không có request-id xuyên suốt API ↔ worker; đối chiếu bằng `source_id` và
  thời điểm.
- Access token (60 phút) là JWT không trạng thái: đăng xuất thu hồi refresh
  token ngay, nhưng access token đang có vẫn dùng được tới khi hết hạn.
- Let's Encrypt cần cổng 80 mở ra Internet để xác thực; sau tường lửa nội bộ
  thì dùng chứng chỉ tự ký của Caddy hoặc cấp chứng chỉ thủ công.
