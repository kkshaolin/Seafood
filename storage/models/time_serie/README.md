# Time-series model artifacts

โฟลเดอร์นี้มี ARIMA pickle/metadata ที่ tracked:

- `arima.pkl`
- `arima_Frozen_Seafood.json` และ `.pkl`
- `arima_Frozen_Shrimp.json` และ `.pkl`
- `arima_premium_shrimp.pkl`

Forecast code สร้าง model path จาก product name และมี special case สำหรับ `Premium_White_Shrimp`; ตรวจ path และ metadata ก่อนนำ artifact ไปใช้งาน.
