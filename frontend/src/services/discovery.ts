import { apiClient } from '@/lib/api';
import type { DouyinMetadataResponse, ScannedFile } from '@/types';

export const fetchMetadata = async (url: string, maxCounts: number = 10, signal?: AbortSignal): Promise<DouyinMetadataResponse> => {
  const response = await apiClient.get(`/douyin/metadata?url=${encodeURIComponent(url)}&max_counts=${maxCounts}`, { signal });
  return response.data;
};

export const selectFolder = async (signal?: AbortSignal): Promise<{ directory: string }> => {
  const response = await apiClient.post('/tasks/transcribe/select-folder', null, { signal });
  return response.data;
};

export const scanDirectory = async (directory: string, signal?: AbortSignal): Promise<{ directory: string; files: ScannedFile[] }> => {
  const response = await apiClient.post('/tasks/transcribe/scan', { directory }, { signal });
  return response.data;
};

export const triggerLocalTranscribe = async (
  filePaths: string[],
  deleteAfter: boolean = false,
  directoryRoot?: string,
  signal?: AbortSignal
): Promise<{ task_id: string }> => {
  const response = await apiClient.post('/tasks/transcribe/local', { file_paths: filePaths, delete_after: deleteAfter, directory_root: directoryRoot || null }, { signal });
  return response.data;
};

export const triggerCreatorTranscribe = async (
  uid: string,
  deleteAfter?: boolean,
  signal?: AbortSignal
): Promise<{ task_id: string; file_count: number }> => {
  const payload: { uid: string; delete_after?: boolean } = { uid };
  if (deleteAfter !== undefined) {
    payload.delete_after = deleteAfter;
  }
  const response = await apiClient.post('/tasks/transcribe/creator', payload, { signal });
  return response.data;
};
