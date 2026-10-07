# Grafana provisioning

- `datasources.yml` ประกาศ data sources ที่ provision ให้ Grafana
- `dashboards.yml` ระบุ provider สำหรับไฟล์ dashboard
- `dashboards/` มี dashboard JSON และ provider configuration อีกชุดที่ถูก mount จาก Compose

ให้ตรวจ mount paths ใน `compose.yml` และ configuration ในไฟล์ก่อนแก้ provisioning.
