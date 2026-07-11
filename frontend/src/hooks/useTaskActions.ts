import { toast } from 'sonner';
import {
  getTaskStatus,
  clearTaskHistory,
  getTaskHistory,
  retryFailedSubtasks,
  triggerBatchPipeline,
  triggerCreatorDownload,
  triggerDownloadBatch,
  triggerFullSyncFollowing,
  triggerLocalTranscribe,
  pauseTask,
  resumeTask,
  cancelTask,
  deleteTask,
} from '@/lib/api';
import { useStore } from '@/store/useStore';
import type { Task } from '@/types';

function parsePayload(payload?: string): Record<string, unknown> | null {
  if (!payload) return null;
  try {
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

export function useTaskActions() {
  const handleClearHistory = async () => {
    try {
      await clearTaskHistory();
      const { setTasks } = useStore.getState();
      const freshTasks = await getTaskHistory();
      setTasks(freshTasks);
      toast.success('已清除历史任务');
    } catch {
      // interceptor already toasts
    }
  };

  const handleRetry = async (task: Task) => {
    let payload = parsePayload(task.payload);
    try {
      try {
        const fresh = await getTaskStatus(task.task_id);
        if (fresh.payload) {
          payload = parsePayload(fresh.payload) || payload;
        }
      } catch {
        void 0;
      }

      // 部分失败任务：只重试失败子任务，避免重跑已成功的部分（也避开
      // rerunTask 对 PARTIAL_FAILED 的 409 限制）。
      if (task.status === 'PARTIAL_FAILED') {
        try {
          const data = await retryFailedSubtasks(task.task_id);
          toast.success(`已派发新任务，仅重试 ${data.file_count} 个失败视频`);
          return;
        } catch {
          // 退回到全量重试（下面的分支会处理）
        }
      }

      if (task.task_type === 'pipeline' && payload) {
        const url = payload.url;
        if (typeof url === 'string' && url) {
          const maxCounts = (payload.max_counts as number) || 5;
          await triggerBatchPipeline([url], maxCounts);
          toast.success('已重新提交下载并转写任务');
          return;
        }
        const urls = payload.video_urls;
        if (Array.isArray(urls)) {
          await triggerBatchPipeline(urls as string[]);
          toast.success('已重新提交下载并转写任务');
          return;
        }
      }

      if (task.task_type === 'local_transcribe' && payload) {
        const paths = payload.file_paths;
        if (Array.isArray(paths) && paths.length > 0) {
          const deleteAfter = (payload.delete_after as boolean) || false;
          const directoryRoot = payload.directory_root as string | undefined;
          await triggerLocalTranscribe(paths as string[], deleteAfter, directoryRoot);
          toast.success('已重新提交本地转写任务');
          return;
        }
      }

      if (task.task_type === 'creator_transcribe' && payload) {
        const uid = payload.creator_uid;
        if (typeof uid === 'string' && uid) {
          toast.info('创作者转写任务暂不支持前端重试，请从创作者页面重新发起');
          return;
        }
      }

      if (task.task_type === 'download' && payload) {
        const urls = payload.video_urls;
        if (Array.isArray(urls)) {
          await triggerDownloadBatch(urls as string[]);
          toast.success('已重新提交下载任务');
          return;
        }
      }

      if ((task.task_type === 'creator_sync_incremental' || task.task_type === 'creator_sync_full') && payload) {
        const uid = payload.uid;
        if (typeof uid === 'string') {
          const mode = task.task_type === 'creator_sync_full' ? 'full' : 'incremental';
          await triggerCreatorDownload(uid, mode);
          toast.success('已重新提交创作者同步任务');
          return;
        }
      }

      if (task.task_type.startsWith('full_sync') && payload) {
        const mode = task.task_type === 'full_sync_full' ? 'full' : 'incremental';
        await triggerFullSyncFollowing(mode);
        toast.success('已重新提交全量同步任务');
        return;
      }

      toast.error('无法重试此任务（缺少原始参数）');
    } catch {
      // interceptor already toasts
    }
  };

  const handlePause = async (task: Task) => {
    try {
      await pauseTask(task.task_id);
      const { updateTask } = useStore.getState();
      updateTask({ task_id: task.task_id, status: 'PAUSED' });
      // 再拉一次，避免与 worker 竞态后 UI 状态不一致
      try {
        const fresh = await getTaskStatus(task.task_id);
        updateTask({ ...fresh, task_id: task.task_id });
      } catch {
        /* keep optimistic PAUSED */
      }
      toast.success('任务已暂停', { description: '继续时将从头执行，非断点续传' });
    } catch {
      // interceptor already toasts
    }
  };

  const handleResume = async (task: Task) => {
    try {
      await resumeTask(task.task_id);
      const { updateTask } = useStore.getState();
      updateTask({ task_id: task.task_id, status: 'RUNNING', progress: 0 });
      try {
        const fresh = await getTaskStatus(task.task_id);
        updateTask({ ...fresh, task_id: task.task_id });
      } catch {
        /* keep optimistic RUNNING */
      }
      toast.success('任务已恢复', { description: '将从头重新执行工作流' });
    } catch {
      // interceptor already toasts
    }
  };

  const handleCancel = async (task: Task) => {
    try {
      await cancelTask(task.task_id);
      const { updateTask } = useStore.getState();
      updateTask({ task_id: task.task_id, status: 'CANCELLED' });
      try {
        const fresh = await getTaskStatus(task.task_id);
        updateTask({ ...fresh, task_id: task.task_id });
      } catch {
        /* keep optimistic CANCELLED */
      }
      toast.success('已停止任务');
    } catch {
      // interceptor already toasts
    }
  };

  const handleDelete = async (task: Task) => {
    try {
      await deleteTask(task.task_id);
      const { tasks, setTasks } = useStore.getState();
      setTasks(tasks.filter((t) => t.task_id !== task.task_id));
      toast.success('已删除任务');
    } catch {
      // interceptor already toasts
    }
  };

  return { handleClearHistory, handleRetry, handlePause, handleResume, handleCancel, handleDelete };
}
