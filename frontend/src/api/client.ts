import axios from 'axios';

// ใช้ Axios client ตัวเดียวร่วมกัน เพื่อให้ทุก API call ใช้ base URL และการตั้งค่าเดียวกัน
// ใน Docker เส้นทาง /api ถูกส่งต่อไป backend โดย Vite (โหมดพัฒนา) หรือ Nginx (โหมด production)
const baseURL = import.meta.env.VITE_API_BASE_URL || '/api';

export const apiClient = axios.create({
  baseURL,
  // กำหนด JSON เป็นรูปแบบข้อมูลเริ่มต้น; ฟังก์ชันอัปโหลดไฟล์จะเปลี่ยนเป็น multipart/form-data
  headers: {
    'Content-Type': 'application/json',
  },
});
