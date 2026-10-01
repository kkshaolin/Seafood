import { apiClient } from './client';

// กำหนดข้อมูลนำเข้าที่ใช้เทียบสต็อกปัจจุบัน/ค่าพยากรณ์กับเกณฑ์ความเสี่ยง
export interface RiskRequest {
  current_stock: number;
  forecast_stock: number;
  threshold: number;
  risk_preference: string;
}

// ให้ backend คำนวณระดับความเสี่ยง เพื่อใช้กฎประเมินชุดเดียวกันทั้งระบบ
export const evaluateRisk = async (payload: RiskRequest) => {
  const res = await apiClient.post('/risk/evaluate', payload);
  return res.data;
};
