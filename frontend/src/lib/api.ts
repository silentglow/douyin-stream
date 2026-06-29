import axios from 'axios';
import { toast } from 'sonner';

const getApiOrigin = () => {
  if (import.meta.env.VITE_API_ORIGIN) {
    return import.meta.env.VITE_API_ORIGIN;
  }
  if (typeof window !== 'undefined') {
    // If running in Vite development mode or on a dev port, use localhost:8000
    if (import.meta.env.DEV || ['5173', '5174', '5175'].includes(window.location.port)) {
      return 'http://localhost:8000';
    }
    return window.location.origin;
  }
  return 'http://localhost:8000';
};

const API_ORIGIN = getApiOrigin();
export const API_BASE_URL = `${API_ORIGIN.replace(/\/$/, '')}/api/v1`;
export const API_WS_URL = `${API_ORIGIN.replace(/^http/, 'ws').replace(/\/$/, '')}/api/v1/tasks/ws`;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 用户主动取消的请求（AbortSignal / 组件卸载 / 路由切换）不算错误
    if (axios.isCancel(error) || error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError') {
      return Promise.reject(error);
    }
    if (axios.isAxiosError(error)) {
      const data = error.response?.data;
      const status = error.response?.status ?? 0;
      const message = data?.message || data?.detail || error.message || '请求失败';

      if (!error.response) {
        // 无 response：广告拦截器（ERR_BLOCKED_BY_CLIENT）、网络断开、后端不可达。
        // 后台轮询请求弹 toast 会打扰用户，仅 console.error 记录。
        // 用户主动操作的请求由业务层 try/catch 自行提示。
        console.error('Network Error:', error.config?.url, error.message);
      } else if (status >= 500) {
        toast.error(`服务器错误: ${message}`);
      } else if (status >= 400) {
        toast.error(message);
      }
    }
    return Promise.reject(error);
  }
);

export type {
  Creator,
  Asset,
  Task,
  ScheduleTask,
  ScannedFile,
  DouyinVideoMeta,
  DouyinCreatorMeta,
  DouyinMetadataResponse,
  QwenStatusAccount,
  QwenStatusResponse,
} from '@/types';

export {
  getCreators,
  addCreator,
  deleteCreator,
  toggleCreatorAutoSync,
} from '@/services/creators';

export {
  getAssets,
  getAssetsByCreator,
  getRecentTranscripts,
  searchAssets,
  getAssetTranscript,
  deleteAsset,
  bulkDeleteAssets,
  cleanupMissingAssets,
  markAsset,
  bulkMarkAssets,
  exportTranscripts,
  getAssetFileUrl,
  browseAssetFolder,
} from '@/services/assets';
export type { FolderFile, FolderBrowseResult } from '@/services/assets';

export {
  getTaskHistory,
  getTaskStatus,
  pauseTask,
  resumeTask,
  cancelTask,
  rerunTask,
  retryFailedSubtasks,
  retryFailedAssets,
  setAutoRetry,
  clearTaskHistory,
  deleteTask,
  retryCreatorTranscribeCleanup,
  triggerPipeline,
  triggerBatchPipeline,
  triggerDownloadBatch,
  triggerCreatorDownload,
  triggerFullSyncFollowing,
  recoverAwemeAndTranscribe,
  getFailureSummary,
} from '@/services/tasks';
export type { FailureSummary, FailureBucket } from '@/services/tasks';

export {
  getSettings,
  updateQwenKey,
  addQwenAccount,
  deleteQwenAccount,
  updateQwenAccountRemark,
  updateQwenAccountCookie,
  rehydrateQwenAccounts,
  addDouyinAccount,
  deleteDouyinAccount,
  updateDouyinAccountRemark,
  addBilibiliAccount,
  deleteBilibiliAccount,
  updateBilibiliAccountRemark,
  updateGlobalSettings,
  getQwenStatus,
  claimQwenQuota,
} from '@/services/settings';

export {
  getSchedules,
  addSchedule,
  toggleSchedule,
  deleteSchedule,
  runScheduleNow,
} from '@/services/scheduler';

export {
  fetchMetadata,
  selectFolder,
  scanDirectory,
  triggerLocalTranscribe,
} from '@/services/discovery';

export {
  globalSearch,
} from '@/services/search';
export type { SearchResult } from '@/services/search';

export {
  getDashboard,
} from '@/services/dashboard';
export type { DashboardData, HealthCheck } from '@/services/dashboard';

// ── Transcripts ──
export async function getTranscripts(status: 'all' | 'unread' | 'starred' = 'all', limitOrSignal?: number | AbortSignal) {
  const params: Record<string, string | number> = { status };
  let signal: AbortSignal | undefined;
  if (typeof limitOrSignal === 'number') {
    params.limit = limitOrSignal;
  } else if (limitOrSignal instanceof AbortSignal) {
    signal = limitOrSignal;
  }
  const res = await apiClient.get('/transcripts', { params, signal });
  return res.data;
}
