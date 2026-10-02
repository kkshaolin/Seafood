# Stage 1: Dev stage สำหรับติดตั้ง dependencies และเตรียม source code
FROM node:18-alpine AS dev
WORKDIR /app
# ติดตั้ง dependencies แยกจาก source เพื่อให้ Docker cache ชั้นนี้เมื่อโค้ดเปลี่ยน
COPY package*.json ./
RUN npm install
COPY . .

# Stage 2: Builder stage คอมไพล์ TypeScript และ Vite bundle สำหรับ production
FROM dev AS builder
RUN npm run build

# image ปลายทางมีเฉพาะ Nginx, static SPA และการตั้งค่า proxy ใน nginx.conf
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
