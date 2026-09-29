# Frontend Application

ระบบหน้าบ้าน (Frontend UI) พัฒนาด้วย **React**, **TypeScript**, และ **Vite** พร้อมใช้ **Tailwind CSS** ในการตกแต่งส่วนแสดงผล

## โครงสร้าง
- **`src/`**
  - **`api/`**: ฟังก์ชันเชื่อมต่อกับ Backend API แบ่งตาม Modules (`camera.ts`, `forecast.ts`, `risk.ts`, `stock.ts`, `settings.ts`)
  - **`components/`**: UI Components ย่อย เช่น `Dashboard.tsx` สำหรับแสดงผลรวม
  - **`services/`**: การตั้งค่าและ Interceptor ของ API (`api.ts`)
  - **`App.tsx` / `main.tsx`**: จุดเริ่มต้นและ Router
- **`Dockerfile` / `nginx.conf`**: สำหรับการ Build Production นำไปโฮสต์ด้วย Nginx