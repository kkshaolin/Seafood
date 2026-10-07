# Training worker

`worker.py` เป็น ARQ dispatcher บน `training_queue`; รองรับ `model_type` เป็น `arima` หรือ `yolo` และส่งต่อไปยัง trainer ใน `trainers/`. งานมี timeout หนึ่งชั่วโมงและจำกัด concurrency ไว้หนึ่ง job ตาม `WorkerSettings`.
