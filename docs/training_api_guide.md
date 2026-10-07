# คู่มือ Training API (ARIMA และ YOLO)

คู่มือนี้อิง schema ใน `backend/src/forecasting/schemas.py`, routes ใน `backend/src/forecasting/router.py` และ worker trainers ปัจจุบัน งานฝึกทำงานผ่าน ARQ/Redis; API ตอบ `202 Accepted` พร้อม `job_id` เมื่อ enqueue งานสำเร็จ

## ฝึก ARIMA

**Endpoint:** `POST /api/forecast/train`

ตัวอย่าง request:

```json
{
  "product": "Frozen Shrimp",
  "p": 1,
  "d": 1,
  "q": 1,
  "forecast_horizon": 3
}
```

`product` ต้องไม่ว่าง; `p` รับ 0–10, `d` รับ 0–5, `q` รับ 0–10 และ `forecast_horizon` รับ 1–60 เดือน ค่าเริ่มต้นตาม schema คือ 1, 1, 1 และ 3 ตามลำดับ

งานจะถูกส่งเข้า `training_queue` ในฐานะ `model_type: arima`. Trainer ใช้ inventory จาก `monthly_inventories` และ fallback ไป `daily_inventories`/CSV ตาม implementation พร้อมอ่าน `box_logs` เป็นข้อมูลกล้องเมื่อมีข้อมูล ค่า `warehouse` มีใน request schema แต่ trainer ปัจจุบันไม่รองรับและจะทำให้งานล้มเหลวหากระบุ

ไฟล์โมเดลและ metrics ถูกส่งไป MinIO bucket `models` ภายใต้ prefix `arima/<product>/<job_id>/`; ผลลัพธ์ job มี `model_uri` และข้อมูล metrics ตามผลการฝึกจริง

## ฝึก YOLO

**Endpoint:** `POST /api/forecast/train/yolo`

ตัวอย่าง request:

```json
{
  "dataset_name": "box_v1",
  "class_names": ["delivery_box"],
  "epochs": 10,
  "imgsz": 640,
  "batch": 8,
  "patience": 5
}
```

Default ตาม schema: `dataset_name=box_v1`, `class_names=["delivery_box"]`, `epochs=10`, `imgsz=640`, `batch=8`, `patience=5`. ช่วงค่าที่ตรวจสอบคือ epochs 1–1000, image size 32–2048, batch 1–256 และ patience 1–100

Trainer ค้นหา ZIP ใน MinIO bucket `datasets` โดยลอง key `yolo/<dataset_name>/<dataset_name>.zip`, `yolo/<dataset_name>.zip` และ `<dataset_name>.zip`; หากไม่พบจะลอง local path `storage/data/<dataset_name>`. Dataset ต้องมีโฟลเดอร์ภาพ train ในรูปแบบ `train/images` หรือ `images/train` และต้องมี training images จริง งานจะ error เมื่อไม่พบ dataset หรือไม่มีภาพ ไม่ได้สร้าง dummy dataset

ผลลัพธ์ของงานถูกเก็บใน MinIO bucket `models` ภายใต้ `yolo/<dataset_name>/<job_id>/`; URI ของโมเดล best ที่ trainer คืนมีรูปแบบ `minio://models/yolo/<dataset_name>/<job_id>/weights/best.pt`

## ตรวจสถานะงาน

**Endpoint:** `GET /api/forecast/{job_id}`

สถานะที่ router ส่งกลับได้แก่ `queued`, `running`, `completed` และ `failed`; job ที่ไม่พบตอบ HTTP 404. เมื่อสำเร็จ `result` มีข้อมูลที่ worker คืนมา; เมื่อ failure `result` เป็น `null` และมีข้อความใน `error`. สำหรับ forecast job response อาจมี sampled-frame/detection fields และ `sampling_error` เพิ่มเติม

## ข้อกำหนดก่อนรัน

- Redis และ worker ที่ตรง queue ต้องทำงานและเชื่อมต่อได้
- ARIMA ต้องมีข้อมูล inventory ในฐานข้อมูลหรือ CSV fallback ที่ worker หาได้
- YOLO ต้องมี dataset ตามชื่อและโครงสร้างที่ trainer รองรับ; ไฟล์ `storage/data/warehouse_box_dataset/data.yaml` เพียงไฟล์เดียวไม่ใช่ dataset ที่มีภาพฝึกครบ
- การฝึก YOLO อาจใช้ base weights จาก MinIO/local path ตามที่ระบุใน `yolo_trainer.py`; การมี training dataset อย่างเดียวไม่ได้ยืนยันว่า camera inference จะมี weights พร้อม

ค่าคำขอและผลลัพธ์ที่แน่นอนให้ตรวจ schema และ trainer source โดยตรงก่อน integrate.
