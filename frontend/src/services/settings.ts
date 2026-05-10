import { apiClient } from '@/lib/api';

export const getSettings = async (signal?: AbortSignal): Promise<{
  qwen_configured: boolean;
  douyin_accounts: Array<{id: string; status: string; last_used: string | null; remark: string; create_time: string}>;
  qwen_accounts: Array<{id: string; status: string; last_used: string | null; remark: string; create_time: string}>;
  bilibili_accounts: Array<{id: string; status: string; last_used: string | null; remark: string; create_time: string}>;
  global_settings: {concurrency: number; auto_delete: boolean; auto_transcribe: boolean; export_format: string};
  status_summary: {
    qwen_ready: boolean;
    douyin_ready: boolean;
    douyin_accounts_count: number;
    douyin_primary_configured: boolean;
    douyin_cookie_source: 'config' | 'pool' | 'none';
    qwen_accounts_count: number;
    bilibili_accounts_count: number;
    can_download: boolean;
    can_transcribe: boolean;
    can_run_pipeline: boolean;
  };
}> => {
  const response = await apiClient.get('/settings', { signal });
  return response.data;
};

export const updateQwenKey = async (cookieString: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.post('/settings/qwen', { cookie_string: cookieString }, { signal });
  return response.data;
};

export const addQwenAccount = async (
  cookieString: string,
  remark?: string,
  signal?: AbortSignal
): Promise<import('@/types').AddQwenAccountResponse> => {
  const response = await apiClient.post('/settings/qwen/accounts', { cookie_string: cookieString, remark: remark || '' }, { signal });
  return response.data;
};

export const deleteQwenAccount = async (accountId: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.delete(`/settings/qwen/accounts/${accountId}`, { signal });
  return response.data;
};

export const updateQwenAccountRemark = async (accountId: string, remark: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.put(`/settings/qwen/accounts/${accountId}/remark`, { remark }, { signal });
  return response.data;
};

export const addDouyinAccount = async (cookieString: string, remark?: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.post('/settings/douyin', { cookie_string: cookieString, remark: remark || '' }, { signal });
  return response.data;
};

export const deleteDouyinAccount = async (accountId: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.delete(`/settings/douyin/${accountId}`, { signal });
  return response.data;
};

export const updateDouyinAccountRemark = async (accountId: string, remark: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.put(`/settings/douyin/${accountId}/remark`, { remark }, { signal });
  return response.data;
};

export const addBilibiliAccount = async (cookieString: string, remark?: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.post('/settings/bilibili/accounts', { cookie_string: cookieString, remark: remark || '' }, { signal });
  return response.data;
};

export const deleteBilibiliAccount = async (accountId: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.delete(`/settings/bilibili/accounts/${accountId}`, { signal });
  return response.data;
};

export const updateBilibiliAccountRemark = async (accountId: string, remark: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.put(`/settings/bilibili/accounts/${accountId}/remark`, { remark }, { signal });
  return response.data;
};

export const updateGlobalSettings = async (concurrency: number | undefined, autoDelete: boolean, autoTranscribe: boolean, exportFormat?: string, signal?: AbortSignal): Promise<unknown> => {
  const payload: Record<string, unknown> = { auto_delete: autoDelete, auto_transcribe: autoTranscribe };
  if (concurrency !== undefined) {
    payload.concurrency = concurrency;
  }
  if (exportFormat !== undefined) {
    payload.export_format = exportFormat;
  }
  const response = await apiClient.post('/settings/global', payload, { signal });
  return response.data;
};

export const getQwenStatus = async (signal?: AbortSignal): Promise<import('@/types').QwenStatusResponse> => {
  const response = await apiClient.get('/settings/qwen/status', { signal });
  return response.data;
};

export const claimQwenQuota = async (signal?: AbortSignal) => {
  const response = await apiClient.post('/settings/qwen/claim', null, { signal });
  return response.data;
};
