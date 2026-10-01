import axios from 'axios';

// ตัวห่อ API รุ่นเก่าที่ยังคงเก็บไว้; Dashboard ปัจจุบันนำเข้าฟังก์ชันจาก src/api/* แทน
const api = axios.create({
  baseURL: '/api',
});

// เมธอด forecast รุ่นเก่า; UI ปัจจุบันใช้ฟังก์ชันที่กำหนดชนิดข้อมูลไว้ใน src/api/forecast.ts
export const forecastApi = {
  queueForecast: async (data: { product: string; forecast_horizon: number; p?: number; d?: number; q?: number }) => {
    return api.post('/forecast', data);
  },
  getJobStatus: async (jobId: string) => {
    return api.get(`/forecast/${jobId}`);
  }
};

// backend/src/main.py ยังไม่ได้ลงทะเบียน camera endpoints เหล่านี้ จึงยังเรียกใช้งานจริงไม่ได้
export const cameraApi = {
  getLatestLog: async (cameraId: string) => {
    return api.get(`/camera/${cameraId}/latest`);
  },
  getLogs: async (cameraId: string) => {
    return api.get(`/camera/${cameraId}/logs`);
  }
};

// เมธอด stock รุ่นเก่า; UI ปัจจุบันใช้ src/api/stock.ts และไม่มีปุ่มอัปโหลด CSV ใน Dashboard
export const stockApi = {
  getHistory: async (product: string) => {
    return api.get(`/stock/history?product=${product}`);
  },
  uploadCsv: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/stock/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  }
};
