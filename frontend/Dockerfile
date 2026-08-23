# Ảnh giao diện cho môi trường phát triển.
#
# Cố ý chạy `next dev` chứ không phải bản build production, vì `docker-compose.yml`
# gắn `./frontend` vào `/app`: sửa mã trên máy là thấy ngay trong container. Một
# ảnh production sẽ chứa bản build đông cứng từ lúc `docker build`, và mọi thay
# đổi sau đó bị chính volume che mất — chạy được nhưng luôn hiển thị mã cũ.
#
# Khi triển khai thật thì đổi sang nhiều tầng: `npm ci && npm run build` rồi
# `next start`, và bỏ volume đi.

FROM node:22-slim

ENV NODE_ENV=development \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

# Cài phụ thuộc trước, chép mã sau — đổi mã không phải cài lại toàn bộ.
#
# `node_modules` bị một volume ẩn danh trong compose che lên. Docker nạp volume
# ấy từ nội dung có sẵn trong ảnh ở lần tạo đầu tiên, nên bước này vẫn là thứ
# đưa thư viện vào container.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

# `-H 0.0.0.0` là bắt buộc trong container: mặc định máy chủ dev chỉ lắng nghe
# trên loopback của chính container, nên cổng ánh xạ ra ngoài sẽ không nối được
# tới đâu cả.
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0", "-p", "3000"]
