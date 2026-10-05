import { apiClient } from './client';

// ระบุรูปแบบข้อมูลที่ backend ต้องได้รับเมื่อขอ forecast หรือฝึกโมเดล
export interface ForecastRequestPayload {
  product: string;
  forecast_horizon: number;
  p?: number;
  d?: number;
  q?: number;
  warehouse?: string;
}

// ส่งคำขอ forecast เข้าคิว เพราะการคำนวณใช้เวลานาน; ใช้ job ID ที่ได้มาตรวจผลภายหลัง
export const queueForecast = async (payload: ForecastRequestPayload) => {
  const res = await apiClient.post('/forecast', payload);
  return res.data;
};

// ส่งงานฝึกโมเดลเข้าคิวแยกจากการพยากรณ์ เพื่อเลือกทำแต่ละงานได้ตามต้องการ
export const queueTraining = async (payload: ForecastRequestPayload) => {
  const res = await apiClient.post('/forecast/train', payload);
  return res.data;
};

// ตรวจสถานะงานและอ่านผลเมื่อ worker ประมวลผล job เสร็จ
export const getForecastJobStatus = async (jobId: string) => {
  const res = await apiClient.get(`/forecast/${jobId}`);
  return res.data;
};

// อ่าน forecast ล่าสุดที่บันทึกในฐานข้อมูล เพื่อให้ Dashboard แสดงผลเดิมได้หลัง reload
export const getLatestForecast = async (product: string) => {
  const res = await apiClient.get(`/forecast/latest?product=${product}`);
  return res.data;
};

// ส่งงานฝึกโมเดล YOLO สำหรับ Object Detection เข้าคิว training_queue
export interface YoloTrainRequestPayload {
  dataset_name?: string;
  class_names?: string[];
  epochs?: number;
  imgsz?: number;
  batch?: number;
  patience?: number;
}

export const queueYoloTraining = async (payload: YoloTrainRequestPayload = {}) => {
  const res = await apiClient.post('/forecast/train/yolo', payload);
  return res.data;
};

