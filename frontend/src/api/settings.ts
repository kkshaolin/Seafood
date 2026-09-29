import { apiClient } from './client';

export const getSettings = async () => {
  const res = await apiClient.get('/settings');
  return res.data;
};

export const updateSettings = async (settings: Record<string, string>) => {
  const res = await apiClient.put('/settings', { settings });
  return res.data;
};
