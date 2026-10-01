# Observability configuration

ไฟล์ตั้งค่าในโฟลเดอร์นี้ถูก mount ให้ services ใน Compose ใช้งาน ไม่ใช่ business logic ของแอป:

- `otel-collector.yml`: รับ telemetry จากแอปผ่าน OTLP แล้วส่ง traces ไป Tempo พร้อมเปิด metrics ให้ Prometheus อ่าน
- `prometheus.yml`: ระบุปลายทาง metrics ที่ Prometheus ต้องดึงจาก Collector และความถี่ในการดึง
- `promtail.yml`: ค้นหา log ของ Docker containers ติดป้าย service แล้วส่งข้อมูลไปเก็บใน Loki
- `loki.yml`: กำหนด Loki ให้เก็บ log ลง filesystem ภายในเครื่อง เหมาะกับ stack สำหรับพัฒนา
- `tempo.yml`: เปิดตัวรับ OTLP และระบุที่เก็บ trace blocks/WAL ของ Tempo
- `grafana/datasources.yml`: สร้าง datasource ใน Grafana ให้ค้น metrics, traces, logs และข้อมูล PostgreSQL
- `grafana/dashboards.yml` และ `grafana/dashboards/dashboards.yml`: บอก Grafana ให้อ่าน dashboard definitions จากไฟล์
- `grafana/dashboards/*.json`: นิยามแผง log และ database; JSON ไม่รองรับคอมเมนต์ จึงอธิบายหน้าที่ไว้ในเอกสารนี้

บริการ observability เริ่มจาก `compose.yml`; การ mount dashboard เพิ่มเติมตั้งใน `compose.override.yml` ค่ารหัสผ่านใน datasource เป็นค่าเริ่มต้นสำหรับพัฒนาในเครื่อง ควรเปลี่ยนก่อนนำไปใช้กับระบบอื่น
