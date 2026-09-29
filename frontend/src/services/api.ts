import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
});

// Mock/Structure for Forecasting API
export const forecastApi = {
  queueForecast: async (data: { product: string; forecast_horizon: number; p?: number; d?: number; q?: number }) => {
    return api.post('/forecast', data);
  },
  getJobStatus: async (jobId: string) => {
    return api.get(`/forecast/${jobId}`);
  }
};

// Mock/Structure for Camera Logs API
export const cameraApi = {
  getLatestLog: async (cameraId: string) => {
    return api.get(`/camera/${cameraId}/latest`);
  },
  getLogs: async (cameraId: string) => {
    return api.get(`/camera/${cameraId}/logs`);
  }
};

// Mock/Structure for Stock History API
export const stockApi = {
  getHistory: async (product: string) => {
    return api.get(`/stock/history?product=${product}`);
  },
  uploadCsv: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/stock/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  }
};
