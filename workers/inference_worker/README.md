# Forecast inference worker

`worker.py` ประกาศ ARQ `WorkerSettings` สำหรับ `forecasting_queue` และรับ `run_forecast_task`. งานพยายามเรียก camera sampling ก่อน แล้วสร้าง `ForecastRequest` และใช้ `ForecastingService` เพื่อสร้าง/บันทึก forecast.

`forecast_model/` มี preprocessing, ARIMA routines, metrics และ service orchestration. Worker ใช้ backend models/session โดยเพิ่ม `backend/src` เข้า Python import path.
