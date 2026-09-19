# ใช้ Base Image Python 3.10 ธรรมดา แล้วโหลด PyTorch ล่าสุดที่มี CUDA 12.4
FROM python:3.10-slim

# ตั้งค่า environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TRANSFORMERS_CACHE=/tmp/transformers_cache
ENV HF_DATASETS_CACHE=/tmp/datasets_cache

WORKDIR /app

# ติดตั้ง System Dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    curl \
    htop \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ติดตั้ง Python Dependencies
COPY requirements.txt ./

# ติดตั้ง PyTorch ใหม่ล่าสุด (CUDA 12.4) รองรับการ์ดจอรุ่นใหม่
RUN pip install --no-cache-dir torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu124
RUN pip install --no-cache-dir -r requirements.txt



# คัดลอก Source Code
COPY *.py ./

# สร้างโฟลเดอร์ที่จำเป็น
RUN mkdir -p /app/storage/data \
             /app/storage/logs \
             /app/storage/models \
             /tmp/transformers_cache \
             /tmp/datasets_cache

# Health Check
HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=3 \
    CMD pgrep -f arq || exit 1

# คำสั่งรัน ARQ Worker
CMD ["python", "-m", "arq", "worker.WorkerSettings"]