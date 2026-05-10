import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import {
  addCreator,
  deleteCreator,
  getSchedules,
  addSchedule,
  toggleSchedule,
  triggerCreatorDownload,
  triggerFullSyncFollowing,
  retryFailedAssets,
  type ScheduleTask,
  type Creator,
} from '@/lib/api';
import { triggerCreatorTranscribe } from '@/services/discovery';

interface UseCreatorsActionsParams {
  storeFetchCreators: (force?: boolean) => Promise<Creator[]>;
  fetchInitialTasks: () => Promise<void>;
  lastCompletedTaskTime: number;
}

export function useCreatorsActions({
  storeFetchCreators,
  fetchInitialTasks,
  lastCompletedTaskTime,
}: UseCreatorsActionsParams) {
  const [loading, setLoading] = useState(true);
  const [downloadingCreators, setDownloadingCreators] = useState<Record<string, 'incremental' | 'full' | null>>({});
  const [confirmDelete, setConfirmDelete] = useState<{ uid: string; nickname: string } | null>(null);
  const [deletingUids, setDeletingUids] = useState<Set<string>>(new Set());
  const [transcribingUids, setTranscribingUids] = useState<Set<string>>(new Set());
  const [retryingFailedUids, setRetryingFailedUids] = useState<Set<string>>(new Set());
  const [newCreatorUrl, setNewCreatorUrl] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [scheduleTask, setScheduleTask] = useState<ScheduleTask | null>(null);

  const fetchCreators = () => {
    storeFetchCreators().finally(() => setLoading(false));
  };

  const reloadCreators = () => {
    storeFetchCreators(true).finally(() => setLoading(false));
  };

  const fetchSchedule = () => {
    getSchedules()
      .then((tasks) => {
        const scanTask = tasks.find((t) => t.task_type === 'scan_all_following');
        setScheduleTask(scanTask || null);
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchCreators();
    fetchSchedule();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastCompletedTaskTime]);

  const handleAddCreator = async (e: React.FormEvent) => {
    e.preventDefault();
    let processedUrl = newCreatorUrl.trim();
    if (!processedUrl) return;
    if (!processedUrl.startsWith('http://') && !processedUrl.startsWith('https://')) {
      processedUrl = `https://${processedUrl}`;
    }

    setIsAdding(true);
    try {
      const result = await addCreator(processedUrl);
      toast.success(result.status === 'created' ? `已添加创作者: ${result.creator.nickname}` : '该创作者已在列表中');
      setNewCreatorUrl('');
      reloadCreators();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      toast.error(`添加创作者失败: ${msg}`);
    } finally {
      setIsAdding(false);
    }
  };

  const handleUnfollow = async (uid: string) => {
    setDeletingUids((prev) => new Set(prev).add(uid));
    try {
      await deleteCreator(uid);
      toast.success('创作者及关联素材已删除');
      reloadCreators();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      toast.error(`删除创作者失败: ${msg}`);
    } finally {
      setDeletingUids((prev) => {
        const next = new Set(prev);
        next.delete(uid);
        return next;
      });
    }
  };

  const handleDownload = async (uid: string, nickname: string, mode: 'incremental' | 'full') => {
    if (downloadingCreators[uid]) return;
    setDownloadingCreators((prev) => ({ ...prev, [uid]: mode }));
    try {
      const result = await triggerCreatorDownload(uid, mode);
      toast.success(`已开始${mode === 'full' ? '全量' : '增量'}同步 ${nickname || uid}`, {
        description: `任务 ID: ${result.task_id}`,
      });
      await fetchInitialTasks();
    } catch {
      toast.error(`无法开始同步 ${nickname || uid}`);
    } finally {
      setDownloadingCreators((prev) => ({ ...prev, [uid]: null }));
    }
  };

  const handleTranscribe = async (uid: string, nickname: string, deleteAfter?: boolean) => {
    if (transcribingUids.has(uid)) return;
    setTranscribingUids((prev) => new Set(prev).add(uid));
    try {
      const result = await triggerCreatorTranscribe(uid, deleteAfter);
      toast.success(`已开始转写 ${nickname || uid} 的 ${result.file_count} 个待处理素材`, {
        description: `任务 ID: ${result.task_id}`,
      });
      await fetchInitialTasks();
    } catch {
      // interceptor already toasts
    } finally {
      setTranscribingUids((prev) => {
        const next = new Set(prev);
        next.delete(uid);
        return next;
      });
    }
  };

  const handleRetryFailed = async (uid: string, nickname: string) => {
    if (retryingFailedUids.has(uid)) return;
    setRetryingFailedUids((prev) => new Set(prev).add(uid));
    try {
      const result = await retryFailedAssets({ creator_uid: uid });
      toast.success(`已重试 ${nickname || uid} 的 ${result.file_count} 个失败素材`, {
        description: result.missing_file_assets?.length
          ? `任务 ID: ${result.task_id}（${result.missing_file_assets.length} 个文件已不在磁盘上，跳过）`
          : `任务 ID: ${result.task_id}`,
      });
      await fetchInitialTasks();
      reloadCreators();
    } catch {
      // interceptor already toasts
    } finally {
      setRetryingFailedUids((prev) => {
        const next = new Set(prev);
        next.delete(uid);
        return next;
      });
    }
  };

  const handleFullSyncNow = async () => {
    try {
      const result = await triggerFullSyncFollowing();
      toast.success('已开始全量同步所有创作者', { description: `任务 ID: ${result.task_id}` });
      await fetchInitialTasks();
    } catch {
      // interceptor already toasts;
    }
  };

  const handleToggleSchedule = async (enabled: boolean) => {
    try {
      if (scheduleTask) {
        await toggleSchedule(scheduleTask.task_id, enabled);
      } else {
        await addSchedule('0 2 * * *', enabled);
      }
      toast.success(enabled ? '定时同步已开启' : '定时同步已关闭');
      fetchSchedule();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      toast.error(`更新定时任务失败: ${msg}`);
    }
  };

  return {
    loading,
    downloadingCreators,
    confirmDelete,
    deletingUids,
    transcribingUids,
    retryingFailedUids,
    newCreatorUrl,
    isAdding,
    scheduleTask,
    setNewCreatorUrl,
    setConfirmDelete,
    handleAddCreator,
    handleUnfollow,
    handleDownload,
    handleTranscribe,
    handleRetryFailed,
    handleFullSyncNow,
    handleToggleSchedule,
  };
}
