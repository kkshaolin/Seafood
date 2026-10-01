# Stage 1: Builder - ติดตั้ง dependencies ให้เร็วที่สุดด้วย uv
FROM python:3.11-slim AS builder

WORKDIR /build

# ติดตั้ง System Dependencies ที่จำเป็นตอน build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ติดตั้ง uv
RUN pip install --no-cache-dir uv

# คัดลอกเฉพาะไฟล์ dependencies ก่อน เพื่อใช้งาน Docker Cache
COPY requirements.txt ./

# ติดตั้ง Dependencies ลงใน System ของ builder stage
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Stage 2: Production
FROM python:3.11-slim

# ตั้งค่า Environment Variables
ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Bangkok \
    TRANSFORMERS_CACHE=/tmp/transformers_cache \
    HF_DATASETS_CACHE=/tmp/datasets_cache

# สร้าง User ที่ไม่ใช่ Root เพื่อความปลอดภัย (Security Best Practice)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# คัดลอก Python Packages จาก Builder Stage (เพื่อความรวดเร็วและ Image ขนาดเล็ก)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# คัดลอก Source Code
# เนื่องจากมีการแบ่ง Worker เป็น 3 โฟลเดอร์ (data_worker, inference_worker, training_worker) 
COPY data_worker/ ./data_worker/
COPY inference_worker/ ./inference_worker/
COPY training_worker/ ./training_worker/

# สร้างโฟลเดอร์ที่จำเป็นและตั้งสิทธิ์ให้ appuser
RUN mkdir -p /app/storage/data \
             /app/storage/logs \
             /app/storage/models \
             /tmp/transformers_cache \
             /tmp/datasets_cache \
    && chown -R appuser:appuser /app /tmp/transformers_cache /tmp/datasets_cache

# สลับไปใช้ appuser
USER appuser

# Health Check สำหรับ ARQ Worker
HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=3 \
    CMD pgrep -f arq || exit 1

# คำสั่งเริ่มต้น (สามารถถูก Override จาก compose.yml ได้)
CMD ["python", "-m", "arq", "inference_worker.worker.WorkerSettings"]