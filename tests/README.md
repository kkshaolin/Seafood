# Tests

- `test_unit_reliability.py` ตรวจ validation ของ forecast/training schemas, metrics, job status, data/model errors และการจัดการ dependency failure
- `test_pipeline_integration.py` เรียก HTTP API ที่ `http://localhost:8000` และตรวจ health, stock, camera, forecast/job flows

Integration tests ต้องมี backend และบริการ/worker ที่เกี่ยวข้องทำงานอยู่ก่อน; ผลทดสอบขึ้นกับข้อมูลและ configuration ของ environment นั้น.
