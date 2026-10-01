import { apiClient } from './client';

// รวมฟังก์ชันเรียก API ด้านสต็อกไว้จุดเดียว เพื่อให้คอมโพเนนต์ไม่ต้องรู้รายละเอียด URL
// Dashboard ใช้ summary/history ส่วนการอ่านรายชื่อสินค้าและอัปโหลดมี API รองรับแต่ยังไม่มีปุ่มใน UI
export const getStock = async () => {
  const res = await apiClient.get('/stock');
  return res.data;
};

export const getStockSummary = async () => {
  const res = await apiClient.get('/stock/summary');
  return res.data;
};

export const getStockProducts = async () => {
  const res = await apiClient.get('/stock/products');
  return res.data;
};

export const getStockHistory = async (product: string) => {
  const res = await apiClient.get(`/stock/history?product=${product}`);
  return res.data;
};

// Backend ยังมี endpoint นำเข้า CSV แต่ Dashboard เอาปุ่มอัปโหลดออกแล้ว จึงไม่มีการเรียกฟังก์ชันนี้จากหน้านั้น
export const uploadStockCsv = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post('/stock/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
};
