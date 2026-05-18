import { apiClient, API_BASE_URL } from '@/lib/api';
import type { Asset } from '@/types';

/* 后端返回小写状态字段。这里只做 null 防御，不再转大写 —— 全前端统一按小写处理。 */
function normalizeAsset(asset: Asset): Asset {
  return {
    ...asset,
    transcript_status: asset.transcript_status ?? '',
    video_status: asset.video_status ?? '',
  };
}

export const getAssets = async (limit = 500, signal?: AbortSignal): Promise<Asset[]> => {
  const response = await apiClient.get(`/assets?limit=${limit}`, { signal });
  return (response.data as Asset[]).map(normalizeAsset);
};

export const getAssetsByCreator = async (creatorUid: string, signal?: AbortSignal): Promise<Asset[]> => {
  const response = await apiClient.get(`/assets?creator_uid=${creatorUid}&limit=500`, { signal });
  return (response.data as Asset[]).map(normalizeAsset);
};

export const getRecentTranscripts = async (limit = 10, signal?: AbortSignal): Promise<Asset[]> => {
  const response = await apiClient.get(`/assets?transcript_status=completed&limit=${limit}`, { signal });
  return (response.data as Asset[]).map(normalizeAsset);
};

export const searchAssets = async (query: string, signal?: AbortSignal): Promise<(Asset & { match_type: string })[]> => {
  const response = await apiClient.get(`/assets/search?q=${encodeURIComponent(query)}`, { signal });
  return (response.data as (Asset & { match_type: string })[]);
};

export const getAssetTranscript = async (assetId: string, signal?: AbortSignal): Promise<string> => {
  const response = await apiClient.get(`/assets/${assetId}/transcript`, { signal });
  return response.data.content;
};

export const deleteAsset = async (assetId: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.delete(`/assets/${assetId}`, { signal });
  return response.data;
};

export const bulkDeleteAssets = async (ids: string[], signal?: AbortSignal): Promise<{ status: string; deleted: number }> => {
  const response = await apiClient.post('/assets/bulk_delete', { ids }, { signal });
  return response.data;
};

export const cleanupMissingAssets = async (signal?: AbortSignal): Promise<{ status: string; deleted: number }> => {
  const response = await apiClient.post('/assets/cleanup', null, { signal });
  return response.data;
};

export const markAsset = async (assetId: string, mark: { is_read?: boolean; is_starred?: boolean }, signal?: AbortSignal) => {
  const response = await apiClient.patch(`/assets/${assetId}/mark`, mark, { signal });
  return response.data;
};

export const bulkMarkAssets = async (
  ids: string[],
  mark: { is_read?: boolean; is_starred?: boolean },
  signal?: AbortSignal
): Promise<{ status: string; updated: number }> => {
  const response = await apiClient.post('/assets/bulk_mark', { ids, ...mark }, { signal });
  return response.data;
};

export const exportTranscripts = async (assetIds: string[], signal?: AbortSignal): Promise<void> => {
  const response = await apiClient.post('/assets/export', assetIds, { responseType: 'blob', signal });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'transcripts.zip';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => window.URL.revokeObjectURL(url), 10000);
};

export const getAssetFileUrl = (assetId: string): string => {
  return `${API_BASE_URL}/assets/${assetId}/file`;
};

export interface FolderFile {
  name: string;
  size: number;
  modified: number;
  suffix: string;
}

export interface FolderBrowseResult {
  path: string;
  files: FolderFile[];
}

export const browseAssetFolder = async (assetId: string, signal?: AbortSignal): Promise<FolderBrowseResult> => {
  const response = await apiClient.get(`/assets/${assetId}/folder`, { signal });
  return response.data;
};
