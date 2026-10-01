# ใช้ Node build แอป React ก่อน แล้วนำไฟล์ static ที่ได้ไปให้ Nginx เสิร์ฟ
FROM node:18-alpine AS builder
WORKDIR /app
# ติดตั้ง dependencies แยกจาก source เพื่อให้ Docker cache ชั้นนี้เมื่อโค้ดเปลี่ยน
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# image ปลายทางมีเฉพาะ Nginx, static SPA และการตั้งค่า proxy ใน nginx.conf
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
