import { apiClient } from './client';

// โหลดค่าตั้งค่าจาก backend เพื่อกำหนดค่าเริ่มต้นของ Dashboard และเกณฑ์ประเมินความเสี่ยง
export const getSettings = async () => {
  const res = await apiClient.get('/settings');
  return res.data;
};

// บันทึกค่าที่ผู้ใช้แก้ไขไว้ที่ backend เพื่อให้ยังใช้ค่าเดิมเมื่อเปิดหน้าใหม่
export const updateSettings = async (settings: Record<string, string>) => {
  const res = await apiClient.put('/settings', { settings });
  return res.data;
};
