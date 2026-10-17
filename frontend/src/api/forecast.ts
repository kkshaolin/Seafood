import { apiClient } from './client';

// ระบุรูปแบบข้อมูลที่ backend ต้องได้รับเมื่อขอ forecast หรือฝึกโมเดล (รองรับ SARIMAX & Dual-Model)
export interface ForecastRequestPayload {
  product: string;
  forecast_horizon: number;
  p?: number;
  d?: number;
  q?: number;
  P?: number;
  D?: number;
  Q?: number;
  s?: number;
  model_type?: 'inbound' | 'outbound' | 'total';
  use_exog?: boolean;
  storm_shock_days?: number;
  fx_shock_pct?: number;
  warehouse?: string;
  video_time?: number;
  video_time_a?: number;
  video_time_b?: number;
  timestamp?: number;
}

export interface WhatIfRequestPayload {
  product?: string;
  forecast_horizon?: number;
  storm_days?: number;
  fx_change_pct?: number;
  fishing_ban_active?: boolean;
  price_per_kg_thb?: number;
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

// อ่าน forecast ล่าสุดที่บันทึกในฐานข้อมูล รองรับการแยก Inbound / Outbound / Total
export const getLatestForecast = async (product: string, modelType: string = 'total') => {
  const res = await apiClient.get(`/forecast/latest?product=${encodeURIComponent(product)}&model_type=${modelType}`);
  return res.data;
};

// ดึงดัชนีภายนอกล่าสุด (สภาพอากาศ, ลม, พายุ, ค่าเงินบาท, ราคาน้ำมัน, ข้างขึ้นข้างแรม)
export const getLatestExogenous = async () => {
  const res = await apiClient.get('/forecast/exogenous/latest');
  return res.data;
};

// จำลองสถานการณ์ What-If ด้วย SARIMAX ทันที
export const simulateWhatIf = async (payload: WhatIfRequestPayload) => {
  const res = await apiClient.post('/forecast/simulate', payload);
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
