import { apiClient } from './client';

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
