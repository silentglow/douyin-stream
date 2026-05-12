import axios from 'axios';
import { toast } from 'sonner';

const API_ORIGIN = import.meta.env.VITE_API_ORIGIN ?? 'http://localhost:8000';
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
    if (axios.isAxiosError(error)) {
      const data = error.response?.data;
      const status = error.response?.status ?? 0;
      const message = data?.message || data?.detail || error.message || '请求失败';

      if (status >= 500) {
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
} from '@/services/creators';

export {
  getAssets,
  getAssetsByCreator,
  searchAssets,
  getAssetTranscript,
  deleteAsset,
  bulkDeleteAssets,
  cleanupMissingAssets,
  markAsset,
  bulkMarkAssets,
  exportTranscripts,
} from '@/services/assets';

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
} from '@/services/scheduler';

export {
  fetchMetadata,
  selectFolder,
  scanDirectory,
  triggerLocalTranscribe,
} from '@/services/discovery';

export {
  getDashboard,
} from '@/services/dashboard';
export type { DashboardData, HealthCheck } from '@/services/dashboard';
