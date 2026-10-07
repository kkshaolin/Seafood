# Frontend

Single-page application ที่สร้างด้วย React 18, TypeScript และ Vite ตาม `package.json`.

## หน้าจอและการเชื่อมต่อ

- `src/App.tsx` สลับระหว่าง Dashboard กับ Training Studio
- `src/components/Dashboard.tsx` แสดงข้อมูล stock/forecast/risk และกล้อง Zone A/B; ใช้ API สำหรับข้อมูลสต็อกและกล้อง พร้อมวิดีโอ mock ใน `public/`
- `src/components/TrainingStudio.tsx` ส่งงาน ARIMA/YOLO และเรียก API สำหรับดู/ซิงค์โมเดล Hugging Face
- `src/api/` รวม Axios calls ที่แยกตาม API domain; client ใช้ `/api` เป็นค่าเริ่มต้น
- `index.html`, `src/main.tsx`, `src/index.css` เป็น entry point และ style ของ SPA

Vite dev server ถูกตั้ง port ภายในเป็น `3000` และ proxy `/api` ไป `http://backend:8000`; Compose development map frontend ไว้ที่ host port `8081`. Production Dockerfile build static bundle แล้วให้ Nginx serve และ proxy API ตาม `nginx.conf`.

## คำสั่งจาก `frontend/`

```text
npm run dev
npm run build
npm run lint
npm run preview
```

`build` รัน TypeScript compiler ก่อน Vite build. Dependencies ระบุใน `package.json` และ lockfile.
