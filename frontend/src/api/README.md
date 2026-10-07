# Frontend API clients

`client.ts` สร้าง Axios instance โดยใช้ `VITE_API_BASE_URL` หรือ `/api` เป็น base URL; modules อื่นแยก calls ตาม domain:

- `stock.ts`: stock summary/products/history/upload
- `forecast.ts`: forecast, job status และ training
- `camera.ts`: camera frames/logs
- `settings.ts`: system settings
- `risk.ts`: risk evaluation
- `huggingface.ts`: model status/push/pull/check

เส้นทาง `/api` ถูก proxy โดย Vite ใน development และ Nginx ใน production.
