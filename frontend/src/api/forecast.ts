import { apiClient } from './client';

export interface ForecastRequestPayload {
  product: string;
  forecast_horizon: number;
  p?: number;
  d?: number;
  q?: number;
  warehouse?: string;
}

export const queueForecast = async (payload: ForecastRequestPayload) => {
  const res = await apiClient.post('/forecast', payload);
  return res.data;
};

export const getForecastJobStatus = async (jobId: string) => {
  const res = await apiClient.get(`/forecast/${jobId}`);
  return res.data;
};
