# Storage

พื้นที่เก็บข้อมูลที่ source และ Compose อ้างถึง; ไฟล์ที่ติดตามใน Git ประกอบด้วย:

- `data/csv_file/shrimp_stock_6years_mont.csv`: CSV รายเดือน มีคอลัมน์ `time`, `product`, `boxes_A`, `boxes_B`, `total_boxes`
- `data/csv_file/shrimp_stock_daily_6years.csv`: CSV รายวัน มีคอลัมน์ชุดเดียวกัน
- `data/warehouse_box_dataset/data.yaml`: YOLO dataset configuration สำหรับ class `delivery_box`
- `models/time_serie/`: ARIMA pickle และ JSON metadata
- `.gitkeep` ใน `data/` และ `models/` รักษา directory ไว้ใน Git

ไม่มี YOLO `.pt` weights หรือภาพ/label dataset ใน tracked storage ปัจจุบัน; model และ dataset ที่ worker ต้องใช้จึงต้องจัดเตรียมแยกต่างหาก ดูรายละเอียดใน README ของโฟลเดอร์ย่อยและ [README หลัก](../README.md).
