import { apiClient } from './client';

// กำหนดข้อมูลนำเข้าที่ใช้เทียบสต็อกปัจจุบัน/ค่าพยากรณ์กับค่าตรวจพบจริงจากกล้อง
export interface RiskRequest {
  current_stock?: number;
  forecast_stock: number;
  detected_stock?: number;
  threshold?: number;
  risk_preference?: string;
}

export interface RiskResponse {
  risk_level: 'Normal' | 'Warning' | 'Critical';
  current_stock?: number;
  forecast_stock: number;
  detected_stock?: number;
  diff_percent?: number;
  threshold?: number;
  effective_threshold?: number;
  risk_preference: string;
  reason: string;
}

// ให้ backend คำนวณระดับความเสี่ยง เพื่อใช้กฎประเมินชุดเดียวกันทั้งระบบ
export const evaluateRisk = async (payload: RiskRequest): Promise<RiskResponse> => {
  const res = await apiClient.post<RiskResponse>('/risk/evaluate', payload);
  return res.data;
};
