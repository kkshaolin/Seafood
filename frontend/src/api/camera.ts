import { apiClient } from './client';

// ฟังก์ชันเตรียมไว้สำหรับเชื่อมกล้อง แต่ backend ปัจจุบันยังไม่ได้ลงทะเบียน camera router
// ดังนั้นการเรียก URL เหล่านี้ยังตอบ 404 จนกว่าจะเพิ่ม endpoint ฝั่ง backend
export const uploadCameraImage = async (cameraId: string, file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post(`/camera/${cameraId}/image`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
};

export const getLatestCameraLog = async (cameraId: string) => {
  const res = await apiClient.get(`/camera/${cameraId}/latest`);
  return res.data;
};

export const getCameraLogsHistory = async (cameraId: string) => {
  const res = await apiClient.get(`/camera/${cameraId}/logs`);
  return res.data;
};
