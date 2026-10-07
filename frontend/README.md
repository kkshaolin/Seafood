# Frontend

React + TypeScript single-page application ที่แสดง stock history, forecast, risk summary, settings และ mock camera panel

## Runtime map

- `src/main.tsx`: mount React เข้าสู่ `index.html`
- `src/App.tsx`: root component ปัจจุบันแสดง `Dashboard`
- `src/components/Dashboard.tsx`: โหลดข้อมูล API, จัดรูปประวัติ/forecast และ render cards/charts/settings
- `src/api/`: Axios functions แยกตาม stock, forecast, settings, risk, huggingface และ camera
- `src/index.css`, `tailwind.config.js`, `postcss.config.js`: base style และ CSS build configuration
- `vite.config.ts`: dev server และ `/api` proxy; Docker development ใช้ service name `backend`
- `nginx.conf`: production static hosting และ `/api` proxy
- `Dockerfile`: build static bundle แล้ว copy ไปยัง Nginx image

## Current integration status

Compose development mode (`compose.override.yml`) ใช้ Vite บน <http://localhost:8081/>; production mode ของ `compose.yml` ใช้ Nginx บนพอร์ตเดียวกัน

Dashboard calls settings/stock/forecast/risk endpoints. Camera panel currently shows a local placeholder image; camera API methods are prepared in the frontend but backend does not register camera routes yet. CSV import endpoint/helper remains in source, but the upload control and upload handler have been removed from the Dashboard.

JSON package lock is generated dependency metadata and does not support comments. Build commands require frontend package metadata/dependencies to be present in the working environment.
