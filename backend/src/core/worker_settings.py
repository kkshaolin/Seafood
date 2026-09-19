# https://arq-docs.helpmanual.io/
import asyncio
from arq import create_pool
from arq.worker import Worker
from arq.connections import RedisSettings


REDIS_SETTINGS = RedisSettings(host="localhost",
                               port=6379,
                               password=None,)

async def startup(ctx):                         # ฟังก์ชันนี้จะถูกเรียกใช้เมื่อ Worker เริ่มทำงาน (Startup Hook)
    pass

async def shutdown(ctx):                        # ฟังก์ชันนี้จะถูกเรียกใช้เมื่อ Worker หยุดทำงาน (Shutdown Hook)
    pass

async def simple_work(ctx, *args, **kwargs):    #ทดสอบงาน
    print("[Worker] Processing job...")
    print(f"Job data (args)   : {args}")
    print(f"Job data (kwargs) : {kwargs}")
    print(f"Job ID            : {ctx['job_id']}")
    return {"status": "done", "data": kwargs}

async def main():                               # ฟังก์ชันหลัก (Main) สำหรับการนำคิวงาน (Enqueue) ส่งเข้าไปใน Redis
    pool = await create_pool(REDIS_SETTINGS)   # สร้าง connection pool เพื่อเชื่อมต่อไปยัง Redis

    worker = Worker(
            functions=WorkerSettings.functions,
            redis_pool=pool,
        )
    print("🔧 Starting ARQ Worker...")
    await worker.run()

class WorkerSettings:                           # คลาสตั้งค่าสำหรับตัว Worker (ใช้เมื่อรันคำสั่ง arq ในเทอร์มินัล)
    functions = [simple_work]              # กำหนดรายการฟังก์ชันที่ Worker ตัวนี้สามารถรันได้
    # on_startup = startup                        # กำหนดฟังก์ชันที่จะให้รันตอนเริ่มต้น (มักใช้เตรียม Connection ต่างๆ)
    # on_shutdown = shutdown                      # กำหนดฟังก์ชันที่จะให้รันตอนจบการทำงาน (มักใช้เคลียร์ Connection)
    redis_settings = REDIS_SETTINGS             # นำการตั้งค่า Redis ที่กำหนดไว้ด้านบนมาใช้กับ Worker

if __name__ == '__main__':
    asyncio.run(main())