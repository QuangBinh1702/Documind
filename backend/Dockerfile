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

# Bản PyTorch nào.
#
# Mặc định là bản CHỈ CPU: nó khoảng 200 MB, còn bản CUDA mặc định của PyPI hơn
# 2,5 GB vì mang theo toàn bộ thư viện CUDA. Trên máy phát triển đặt DEVICE=cpu
# thì ngần ấy dung lượng là tải về rồi không dùng.
#
# Máy đích có GPU thì dựng lại bằng:
#   docker compose build --build-arg TORCH_INDEX=https://pypi.org/simple api worker
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu

# Cài phụ thuộc trước, chép mã sau — đổi mã không phải cài lại thư viện.
#
# Cài `torch` riêng và cài TRƯỚC: đặt sau thì pip đã lấy bản CUDA từ PyPI theo
# yêu cầu của `sentence-transformers` rồi, và `--index-url` ở đây không rút lại
# được nữa.
COPY pyproject.toml ./
RUN pip install --upgrade pip \
 && pip install --index-url "${TORCH_INDEX}" torch \
 && pip install -e ".[dev,ml]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
