# Forecast model code

- `service.py`: อ่าน monthly inventory/box logs, เตรียม series, โหลดหรือฝึก ARIMA และบันทึก forecast
- `arima.py`: วิเคราะห์ order, fit และ forecast ด้วย ARIMA
- `preprocessing.py`: ทำความสะอาดและ aggregate series เป็นรายเดือน พร้อม chronological split
- `metrics.py`: MAE/RMSE/MAPE และ Naïve/Seasonal Naïve baselines
- `__init__.py`: package marker

Worker entry point ที่เรียก service อยู่ใน `../worker.py`.
