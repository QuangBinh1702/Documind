#!/usr/bin/env bash
# DocuMind — khôi phục từ một cặp bản sao lưu do backup.sh tạo ra.
#
#   ./infra/backup/restore.sh /var/backups/documind/pg-20260826-030000.dump \
#                             /var/backups/documind/minio-20260826-030000.tar.gz
#
# GHI ĐÈ toàn bộ dữ liệu hiện có. Dừng api và worker trước để không có ai ghi
# vào giữa chừng. Hãy diễn tập một lần trên máy khác trước khi cần thật.
set -euo pipefail

PG_DUMP="${1:?Cần tệp pg-*.dump}"
MINIO_TAR="${2:?Cần tệp minio-*.tar.gz}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.yml -f compose.prod.yml}"

set -a; . ./.env; set +a
POSTGRES_USER="${POSTGRES_USER:-documind}"
POSTGRES_DB="${POSTGRES_DB:-documind}"

echo "Dừng api, worker, minio"
$COMPOSE stop api worker minio

echo "Khôi phục Postgres từ $PG_DUMP"
$COMPOSE exec -T postgres dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
$COMPOSE exec -T postgres createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
$COMPOSE exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner \
  < "$PG_DUMP"

echo "Khôi phục MinIO từ $MINIO_TAR"
docker run --rm \
  -v documind_minio-data:/data \
  -v "$(dirname "$(realpath "$MINIO_TAR")")":/backup:ro \
  alpine:3.20 sh -c "rm -rf /data/* && tar xzf /backup/$(basename "$MINIO_TAR") -C /data"

echo "Khởi động lại"
$COMPOSE up -d minio api worker
echo "Xong. Kiểm tra: curl -fsS https://\$DOMAIN/api/health"
