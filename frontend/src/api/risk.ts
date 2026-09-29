import { apiClient } from './client';

export interface RiskRequest {
  current_stock: number;
  forecast_stock: number;
  threshold: number;
  risk_preference: string;
}

export const evaluateRisk = async (payload: RiskRequest) => {
  const res = await apiClient.post('/risk/evaluate', payload);
  return res.data;
};
