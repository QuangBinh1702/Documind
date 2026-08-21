# DocuMind — lệnh tắt cho các thao tác thường dùng.
# Windows: cài GNU Make, hoặc chép lệnh trong từng target ra chạy tay.

.PHONY: help up down infra logs migrate revision test test-db test-perf lint fmt clean reset

PY := backend/.venv/Scripts/python.exe   # Linux/macOS: backend/.venv/bin/python

help:
	@echo "up        - dung toan bo he thong"
	@echo "infra     - chi dung postgres, redis, minio (du de chay test)"
	@echo "down      - dung tat ca, giu du lieu"
	@echo "reset     - dung tat ca va XOA volume (mat het du lieu)"
	@echo "migrate   - chay alembic upgrade head"
	@echo "revision  - tao migration moi:  make revision M='mo ta'"
	@echo "test      - test khong can ha tang"
	@echo "test-db   - test can postgres/redis/minio dang chay"
	@echo "test-perf - moc hieu nang, CHI co nghia tren may dich 16 GB"
	@echo "lint      - ruff check"
	@echo "fmt       - ruff format"

up:
	docker compose up -d

infra:
	docker compose up -d postgres redis minio minio-init

down:
	docker compose down

# Xoa ca volume. Dung khi doi infra/postgres/init/*.sql — script init chi chay
# khi volume con rong.
reset:
	docker compose down -v

logs:
	docker compose logs -f --tail=100

migrate:
	cd backend && $(CURDIR)/$(PY) -m alembic upgrade head

revision:
	cd backend && $(CURDIR)/$(PY) -m alembic revision -m "$(M)"

test:
	cd backend && $(CURDIR)/$(PY) -m pytest -m "not db and not perf and not ml" -v

test-db:
	cd backend && $(CURDIR)/$(PY) -m pytest -m "db" -v

# Moc hieu nang chi co nghia tren may dich (SPEC.md US-057 AC-8).
test-perf:
	cd backend && $(CURDIR)/$(PY) -m pytest -m "perf" -v

lint:
	cd backend && $(CURDIR)/$(PY) -m ruff check app tests

fmt:
	cd backend && $(CURDIR)/$(PY) -m ruff format app tests

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
