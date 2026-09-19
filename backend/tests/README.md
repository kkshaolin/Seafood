#  Unit Tests (pytest)
ไฟล์นี้อธิบายแนวทางการรันและการเขียน Unit Tests สำหรับ `backend` โดยใช้ `pytest` เป็นหลัก

## รัน Unit Tests (พื้นฐาน)

รันไฟล์ทดสอบเดียว:

```powershell
pytest -q backend/tests/test_example.py
```

รันฟังก์ชันทดสอบเดียวภายในไฟล์:

```powershell
pytest backend/tests/test_example.py::test_function_name -q
```

ตัวเลือกที่มี:
- `-k EXPR` : เลือกรันเทสต์ที่ตรงกับนิพจน์
- `-m MARKER` : รันเทสต์ที่มี marker (เช่น `@pytest.mark.slow`)
- `-x` : หยุดที่ความล้มเหลวครั้งแรก
- `-s` : แสดง stdout/stderr จากเทสต์


## แนวปฏิบัติการเขียนเทสต์
- เขียนเทสต์ให้เล็กและแยกหน้าที่ (unit test) — หลีกเลี่ยงการพึ่งพา external services ใน unit tests
- สำหรับการทดสอบ integration ให้แยกไว้ในโฟลเดอร์หรือใช้ marker เช่น `@pytest.mark.integration`
- ใช้ fixtures เพื่อตั้ง/ล้างข้อมูล (setup/teardown)
- ไม่ควร commit ไฟล์ผลลัพธ์การทดสอบ
