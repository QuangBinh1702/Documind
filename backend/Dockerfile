FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libmagic: xác minh MIME theo NỘI DUNG tệp, không theo phần mở rộng (US-006 AC-5)
# libgl1 + libglib: PyMuPDF và PaddleOCR cần khi render trang thành ảnh
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Cài phụ thuộc trước, chép mã sau — đổi mã không phải cài lại thư viện.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
