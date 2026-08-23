FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libmagic: xác minh MIME theo NỘI DUNG tệp, không theo phần mở rộng (US-006 AC-5)
# libgl1 + libglib: PyMuPDF và PaddleOCR cần khi render trang thành ảnh
# fonts-dejavu-core: PDF xuất ra ở US-040 phải hiển thị đúng tiếng Việt có dấu.
#   Ảnh nền `python:3.12-slim` không có font nào, và 14 font chuẩn của PDF thì
#   không có ký tự tiếng Việt — thiếu gói này thì "Điều" in ra thành ô vuông.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 \
        libgl1 \
        libglib2.0-0 \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Cài phụ thuộc trước, chép mã sau — đổi mã không phải cài lại thư viện.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
