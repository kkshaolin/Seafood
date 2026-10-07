import { apiClient } from './client';

export interface CameraLatestInfo {
  camera_id: string;
  zone: string;
  detected_boxes: number;
  confidence: number;
  last_updated: string;
  next_update_seconds: number;
  interval_seconds: number;
  status: string;
}

export const getCameraFrameUrl = (cameraId: string, timestamp?: number, force: boolean = false): string => {
  const base = import.meta.env.VITE_API_BASE_URL || '/api';
  const query = new URLSearchParams();
  if (timestamp) query.set('t', timestamp.toString());
  if (force) query.set('force', 'true');
  const qs = query.toString();
  return `${base}/camera/${cameraId}/frame${qs ? `?${qs}` : ''}`;
};

export const getCameraSampledFrameUrl = (cameraId: string, key: string, timestamp?: number): string => {
  const base = import.meta.env.VITE_API_BASE_URL || '/api';
  const query = new URLSearchParams({ key });
  if (timestamp) query.set('t', timestamp.toString());
  return `${base}/camera/${cameraId}/sampled-frame?${query.toString()}`;
};

export const uploadCameraImage = async (cameraId: string, file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post(`/camera/${cameraId}/image`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
};

export const getLatestCameraLog = async (cameraId: string): Promise<CameraLatestInfo> => {
  const res = await apiClient.get<CameraLatestInfo>(`/camera/${cameraId}/latest`);
  return res.data;
};

export const getCameraLogsHistory = async (cameraId: string) => {
  const res = await apiClient.get(`/camera/${cameraId}/logs`);
  return res.data;
};
