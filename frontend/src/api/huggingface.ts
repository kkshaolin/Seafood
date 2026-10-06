import { apiClient } from './client';

export interface LocalModelStatus {
  name: string;
  path: string;
  exists: boolean;
  size_mb?: number;
  size_kb?: number;
}

export interface HuggingFaceStatusResponse {
  repo_id: string;
  architecture: string;
  local: {
    yolo_box: LocalModelStatus;
    arima_model: LocalModelStatus;
    arima_metrics: LocalModelStatus;
  };
  huggingface: {
    repo_id: string;
    connected: boolean;
    user: string | null;
    files: string[];
    error: string | null;
  };
  minio: {
    connected: boolean;
    bucket: string;
    objects_count: number;
    error?: string | null;
  };
}

export interface HfActionResult {
  status: string;
  repo_id?: string;
  uploaded_files?: string[];
  downloaded_files?: string[];
  count?: number;
  message?: string;
  cache_status?: string;
}

// ตรวจสอบสถานะ Hugging Face Hub, Local Cache, และ MinIO
export const getHfStatus = async (): Promise<HuggingFaceStatusResponse> => {
  const res = await apiClient.get('/hf/status');
  return res.data;
};

// Publish / Push โมเดลขึ้น Hugging Face Hub
export const pushToHf = async (): Promise<HfActionResult> => {
  const res = await apiClient.post('/hf/push');
  return res.data;
};

// Pull / Sync โมเดลจาก Hugging Face Hub ลง Local & MinIO
export const pullFromHf = async (force: boolean = false): Promise<HfActionResult> => {
  const res = await apiClient.post('/hf/pull', { force });
  return res.data;
};

// Cache-Aside Check: ดึงโมเดลอัตโนมัติหากยังไม่มี
export const checkOrPullHf = async (): Promise<HfActionResult> => {
  const res = await apiClient.post('/hf/check-or-pull');
  return res.data;
};
