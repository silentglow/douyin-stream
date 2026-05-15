import { apiClient } from '@/lib/api';
import type { Creator } from '@/types';

export const getCreators = async (signal?: AbortSignal): Promise<Creator[]> => {
  const response = await apiClient.get('/creators', { signal });
  return response.data;
};

export const addCreator = async (url: string, signal?: AbortSignal): Promise<{status: 'created' | 'exists'; creator: Creator}> => {
  const response = await apiClient.post('/creators', { url }, { signal });
  return response.data;
};

export const deleteCreator = async (creatorUid: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.delete(`/creators/${creatorUid}`, { signal });
  return response.data;
};

export const toggleCreatorAutoSync = async (creatorUid: string, autoSync: boolean, signal?: AbortSignal): Promise<{ status: string; auto_sync: boolean }> => {
  const response = await apiClient.patch(`/creators/${creatorUid}/auto-sync`, { auto_sync: autoSync }, { signal });
  return response.data;
};
