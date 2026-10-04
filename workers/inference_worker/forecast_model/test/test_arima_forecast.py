"""สคริปต์ทดสอบการทำงานของระบบพยากรณ์ ARIMA ในโปรเจค Seafood"""

import asyncio
import os
import sys
from pathlib import Path
import pandas as pd

workspace_root = Path(__file__).resolve().parents[4]
backend_src = workspace_root / "backend" / "src"
workers_root = workspace_root / "workers"

for p in [str(backend_src), str(workers_root), str(workspace_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from inference_worker.forecast_model.service import ForecastingService
from forecasting.schemas import ForecastRequest


class MockSession:
    """Mock Session สำหรับทดสอบโดยไม่ใช้ฐานข้อมูล"""
    async def execute(self, stmt):
        class EmptyResult:
            def all(self):
                return []
        return EmptyResult()
    
    async def commit(self):
        pass

    def add(self, instance):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


async def run_test():
    print("=== เริ่มต้นทดสอบการพยากรณ์ ARIMA (Mock Data Mode) ===")
    
    request_data = ForecastRequest(
        product="Premium_White_Shrimp",
        p=1,
        d=1,
        q=1,
        forecast_horizon=3,
        warehouse=None
    )

    async with MockSession() as session:
        service = ForecastingService(session)
        
        # แทนที่จะเรียกผ่าน get_inventory_data ที่พยายามต่อ DB/ไฟล์ ให้เราดัก Mock ข้อมูลดิบส่งเข้าบริการทันที
        async def mock_get_inventory_data():
            # สร้างข้อมูลอนุกรมเวลารายเดือนจำลองสำหรับเทสโมเดล
            dates = pd.date_range(start="2025-01-01", periods=12, freq="MS")
            quantities = [100.0, 120.0, 110.0, 130.0, 145.0, 160.0, 155.0, 170.0, 185.0, 190.0, 210.0, 220.0]
            return pd.DataFrame({"recorded_at": dates, "quantity": quantities})

        # แทนที่ฟังก์ชันดึงข้อมูลด้วยข้อมูลจำลองชั่วคราว
        service.get_inventory_data = mock_get_inventory_data

        try:
            print("กำลังประมวลผลข้อมูลและรันโมเดล ARIMA...")
            response = await service.run_forecast(request_data)
            
            print("\n=== ผลลัพธ์การพยากรณ์สำเร็จ ===")
            print(f"สินค้า: {response.product}")
            print(f"ชื่อโมเดล: {response.model_name}")
            print(f"ค่าความคลาดเคลื่อน (Metrics): MAE={response.metrics.mae:.2f}, RMSE={response.metrics.rmse:.2f}, MAPE={response.metrics.mape:.2f}%")
            print("รายการพยากรณ์อนาคต:")
            for pt in response.forecast:
                print(f" - วันที่: {pt.date} | ทำนาย: {pt.predicted_value:.2f} (ช่วงความเชื่อมั่น: {pt.lower_bound:.2f} ถึง {pt.upper_bound:.2f})")
                
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการทดสอบ: {e}")


if __name__ == "__main__":
    asyncio.run(run_test())