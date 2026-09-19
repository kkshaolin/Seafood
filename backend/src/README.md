
# Backend `src`

โฟลเดอร์ `src` เป็นที่เก็บซอร์สโค้ดหลักของบริการ Backend (FastAPI) — ทั้ง entry point, router, models, service layer และ helper utilities

- แยกชั้นส่วนของแอปให้ชัดเจนตามแนวทางของเว็บ API: routing, controller, schema, service, และ data layer
- ทำให้ง่ายต่อการทดสอบ (unit / integration) โดยสามารถ mock หรือแยก dependency ได้สะดวก
- รวบรวมโค้ดที่จำเป็นสำหรับรันแอปและ worker ที่เกี่ยวข้อง


## โครงสร้างและคำอธิบายโฟลเดอร์/ไฟล์หลัก

- `api/` — ชั้น API (แบ่งตาม domain)
	- โครงสร้างย่อยโดยทั่วไป:
		- `auth/` — ระบบ Authentication (register, login, token)
			- `controller.py` / `router.py` : รับ request -> validate -> เรียก service
			- `service.py` : ตรรกะเกี่ยวกับผู้ใช้และ JWT (สร้าง token, verify)
			- `repository.py` : ฟังก์ชันเข้าถึง DB เกี่ยวกับ user (CRUD)
			- `schema.py` : Pydantic models สำหรับ request/response (เช่น `UserCreate`, `UserOut`)
			- `model.py` : ถ้ามี model เฉพาะ module นี้ (มักอ้างถึง DB model ใน `models/`)

        - `storage/` — API สำหรับอัปโหลด/ดาวน์โหลดไฟล์ และสั่งงาน storage worker
            - `router.py` : endpoints สำหรับ upload/download
            - เรียก `services/storage.py` เพื่อจัดการ MinIO interaction

        - `training/` — API สำหรับการสั่งงานเทรนโมเดล (Machine Learning)
            - `controller.py` : รับ request สร้าง job_id (สามารถตั้งเวลา scheduled_time)
            - `service.py` : เชื่อมต่อ ARQ Redis เพื่อดึงสถานะหรือ enqueue `train_model` job
            - `schema.py` : โครงสร้าง Request/Response เช่น `TrainingRequest`

		- `users/` — API สำหรับจัดการผู้ใช้งาน (CRUD, profile)
			- รูปแบบไฟล์เหมือน `auth/` แต่เน้นการจัดการข้อมูลผู้ใช้

	- `router.py` เป็นจุดรวม route ในแต่ละ domain; `controller.py` ถ้าแยกจาก router จะเก็บ logic ระดับ HTTP (validate, parse), ส่วน `service.py` เก็บ business logic

- `core/` — การตั้งค่าระบบและคอนฟิกหลัก
	- `config.py` : โหลดคอนฟิกจาก `.env` หรือ environment variables (เช่น DB URL, Redis, MinIO credentials)
	- `database.py` : สร้าง Async Engine, SessionLocal, และ helper สำหรับ dependency injection ของ DB session
	- `worker_settings.py` : ค่าที่เกี่ยวข้องกับ worker/queue (เช่น ARQ, Redis)

- `db/` — ระดับการเชื่อมต่อและ helper สำหรับ database
	- `database.py` : ฟังก์ชันและ context manager สำหรับการเชื่อมต่อ DB ที่ใช้งานร่วมกับ SQLAlchemy Async sessions

- `models/` — SQLAlchemy ORM models (กำหนด structure ของ table) ฟิลด์ที่สำคัญ, constraint, relationship กับตารางอื่น ๆ
    - `student.py` : Model สำหรับ table students

- `services/` — Business logic ที่แยกจาก API layer (ไฟล์ในนี้ควรเป็น logic ที่สามารถทดสอบแยกได้ ไม่ผูกกับ HTTP)
	- `storage.py` : ตัวจัดการการเชื่อมต่อกับ MinIO, ฟังก์ชันอัปโหลด/ดาวน์โหลด, สร้าง presigned URLs

- `utils/` — ฟังก์ชันและคลาสช่วยเหลือทั่วไป (เพื่อไม่ต้องเขียนโค้ดซ้ำๆ ในงานเดิม)
	- `logger.py` : คอนฟิก logger ของแอป (formatters, handlers)

- `main.py` — Entry point ของแอป FastAPI
	- สร้างและคอนฟิก `FastAPI` app (middleware, CORS, exception handlers)
	- รวม router จาก `api.*` และลงทะเบียน health check endpoint (`/health`)

## แนวทางการเขียนโค้ดและการแบ่งชั้น

- แยก `controller/router` กับ `service` เพื่อให้ unit test ง่ายขึ้น: ทดสอบ `service` แยกจาก HTTP layer
- ใช้ Pydantic สำหรับ validation ของ request/response ใน `api/*/schema.py`
- ใช้ dependency injection ของ FastAPI ในการให้ DB session (`Depends(get_db)`) และ security (เช่น `get_current_user`)
- เก็บการตั้งค่าที่เปลี่ยนแปลงในสภาพแวดล้อมไว้ใน `.env` และอ่านผ่าน `core/config.py`


