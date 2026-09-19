# Stage 1: Builder - ติดตั้ง dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

# ติดตั้ง uv (ตัวจัดการ package ที่เร็วมาก)
RUN pip install --no-cache-dir uv

# คัดลอกไฟล์ dependencies ก่อน (เพื่อใช้ cache)
COPY pyproject.toml ./

# ติดตั้ง dependencies ทั้งหมด
RUN uv pip install --system --no-cache-dir -r pyproject.toml

# Stage 2: Production - Image สุดท้าย
FROM python:3.11-slim

# สร้าง user ที่ไม่ใช้ root (เพื่อความปลอดภัย)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# คัดลอก dependencies จาก builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# คัดลอก source code
COPY src/ ./src/

# สร้างโฟลเดอร์ที่จำเป็น
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

# เปลี่ยนไปใช้ user ที่ไม่ใช้ root
USER appuser

# เปิดพอร์ต 8000
EXPOSE 8000

# Health check - ตรวจสอบว่า server พร้อมใช้งานไหม
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# คำสั่งรันแอปพลิเคชัน
CMD ["python", "src/main.py"]