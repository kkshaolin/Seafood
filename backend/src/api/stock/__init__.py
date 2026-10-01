# ส่งออก router ของ stock ไว้ที่ระดับ package เพื่อให้ import จุดรวม API ได้สะดวก
from api.stock.router import router

__all__ = ["router"]
