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

export const queueTraining = async (payload: ForecastRequestPayload) => {
  const res = await apiClient.post('/forecast/train', payload);
  return res.data;
};

export const getForecastJobStatus = async (jobId: string) => {
  const res = await apiClient.get(`/forecast/${jobId}`);
  return res.data;
};

export const getLatestForecast = async (product: string) => {
  const res = await apiClient.get(`/forecast/latest?product=${product}`);
  return res.data;
};
