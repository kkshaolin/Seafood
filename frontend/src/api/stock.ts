import { apiClient } from './client';

export const getStock = async () => {
  const res = await apiClient.get('/stock');
  return res.data;
};

export const getStockSummary = async () => {
  const res = await apiClient.get('/stock/summary');
  return res.data;
};

export const getStockProducts = async () => {
  const res = await apiClient.get('/stock/products');
  return res.data;
};

export const getStockHistory = async (product: string) => {
  const res = await apiClient.get(`/stock/history?product=${product}`);
  return res.data;
};

export const uploadStockCsv = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post('/stock/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
};
