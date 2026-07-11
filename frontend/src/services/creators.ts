import { apiClient } from '@/lib/api';
import type { Creator } from '@/types';

export const getCreators = async (signal?: AbortSignal): Promise<Creator[]> => {
  const response = await apiClient.get('/creators', { params: { limit: 500 }, signal });
  return response.data;
};

export const addCreator = async (url: string, signal?: AbortSignal): Promise<{status: 'created' | 'exists'; creator: Creator}> => {
  const response = await apiClient.post('/creators', { url }, { signal });
  return response.data;
};

export const deleteCreator = async (
  creatorUid: string,
  options?: { keepContent?: boolean; signal?: AbortSignal },
): Promise<{ status: string; mode?: string; message?: string; deleted_assets?: number }> => {
  const keepContent = options?.keepContent ?? false;
  const response = await apiClient.delete(`/creators/${creatorUid}`, {
    params: { keep_content: keepContent },
    signal: options?.signal,
  });
  return response.data;
};

export const toggleCreatorAutoSync = async (creatorUid: string, autoSync: boolean, signal?: AbortSignal): Promise<{ status: string; auto_sync: boolean }> => {
  const response = await apiClient.patch(`/creators/${creatorUid}/auto-sync`, { auto_sync: autoSync }, { signal });
  return response.data;
};

export const bulkSetCreatorAutoSync = async (
  autoSync: boolean,
  signal?: AbortSignal,
): Promise<{ status: string; auto_sync: boolean; updated: number }> => {
  const response = await apiClient.post('/creators/auto-sync/bulk', { auto_sync: autoSync }, { signal });
  return response.data;
};

export const refollowCreator = async (
  creatorUid: string,
  signal?: AbortSignal,
): Promise<{ status: string; refollowed: boolean }> => {
  const response = await apiClient.post(`/creators/${creatorUid}/refollow`, null, { signal });
  return response.data;
};
