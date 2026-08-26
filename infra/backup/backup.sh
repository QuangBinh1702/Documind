#!/usr/bin/env bash
# DocuMind — sao lưu Postgres và MinIO ra một thư mục trên máy chủ.
#
#   ./infra/backup/backup.sh /var/backups/documind
#
# Chạy hằng ngày bằng cron, ví dụ (3 giờ sáng):
#   0 3 * * * cd /opt/documind && ./infra/backup/backup.sh /var/backups/documind >> /var/log/documind-backup.log 2>&1
#
# Giữ 14 bản gần nhất. `model-cache` và `ollama-models` KHÔNG sao lưu — tải lại
# được từ Internet, còn tài liệu và cơ sở dữ liệu thì không.
set -euo pipefail

DICH="${1:?Cần đường dẫn thư mục sao lưu}"
GIU_LAI="${GIU_LAI:-14}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.yml -f compose.prod.yml}"
DAU_THOI_GIAN="$(date +%Y%m%d-%H%M%S)"

# Đọc thông tin kết nối từ .env của dự án.
set -a; . ./.env; set +a
POSTGRES_USER="${POSTGRES_USER:-documind}"
POSTGRES_DB="${POSTGRES_DB:-documind}"

mkdir -p "$DICH"

echo "[$DAU_THOI_GIAN] Postgres → $DICH/pg-$DAU_THOI_GIAN.dump"
$COMPOSE exec -T postgres pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB" \
  > "$DICH/pg-$DAU_THOI_GIAN.dump"

echo "[$DAU_THOI_GIAN] MinIO → $DICH/minio-$DAU_THOI_GIAN.tar.gz"
# Đóng gói thẳng volume: không cần `mc`, và không phụ thuộc MinIO đang chạy.
docker run --rm \
  -v documind_minio-data:/data:ro \
  -v "$DICH":/backup \
  alpine:3.20 tar czf "/backup/minio-$DAU_THOI_GIAN.tar.gz" -C /data .

echo "[$DAU_THOI_GIAN] Dọn bản cũ, giữ $GIU_LAI bản"
ls -1t "$DICH"/pg-*.dump 2>/dev/null | tail -n +$((GIU_LAI + 1)) | xargs -r rm -f
ls -1t "$DICH"/minio-*.tar.gz 2>/dev/null | tail -n +$((GIU_LAI + 1)) | xargs -r rm -f

echo "[$DAU_THOI_GIAN] Xong. $(du -sh "$DICH" | cut -f1) đang dùng."
