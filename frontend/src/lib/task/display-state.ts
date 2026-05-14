import type { Task } from '@/lib/api';
import { taskTimestamp } from './formatters';

const ACTIVE_STATUSES = new Set(['RUNNING', 'PENDING', 'PAUSED']);
const SUCCESS_STATUSES = new Set(['COMPLETED', 'SUCCESS']);
const PARTIAL_STATUSES = new Set(['PARTIAL_FAILED']);
const FAILURE_STATUSES = new Set(['FAILED', 'ERROR', 'CANCELLED']);
const STALE_MINUTES = 20;

export type DisplayTaskState = 'running' | 'success' | 'failed' | 'partial' | 'stale' | 'unknown' | 'paused';

export function parseTaskMessage(payload?: string) {
  if (!payload) return '';
  try {
    const parsed = JSON.parse(payload);
    if (typeof parsed?.msg === 'string') return parsed.msg;
    if (typeof parsed?.message === 'string') return parsed.message;
  } catch {
    return '';
  }
  return '';
}

export function taskTypeLabel(type: string) {
  return (
    {
      pipeline: '下载并转写',
      download: '仅下载',
      local_transcribe: '本地转写',
      creator_transcribe: '创作者转写',
      creator_sync_incremental: '创作者增量同步',
      creator_sync_full: '创作者全量同步',
      full_sync_incremental: '全量增量同步',
      full_sync_full: '全量全量同步',
      scan_all_following: '定时同步',
    }[type] || type
  );
}

export function isTaskStale(task: Task, now = Date.now()) {
  if (!ACTIVE_STATUSES.has(task.status)) return false;
  const ts = taskTimestamp(task);
  if (!ts) return false;
  return now - ts > STALE_MINUTES * 60 * 1000;
}

export function getTaskDisplayState(task: Task): DisplayTaskState {
  if (task.status === 'PAUSED') return 'paused';
  if (isTaskStale(task)) return 'stale';
  if (ACTIVE_STATUSES.has(task.status)) {
    const msg = parseTaskMessage(task.payload);
    if (msg.includes('全部下载完成') || msg.includes('下载完成') || msg.includes('全部转写完成') || msg.includes('转写完成')) {
      return 'success';
    }
    if (task.task_type === 'download') {
      try {
        const parsed = JSON.parse(task.payload);
        const pp = parsed?.pipeline_progress;
        if (pp?.download && typeof pp.download.done === 'number' && typeof pp.download.total === 'number'
            && pp.download.total > 0 && pp.download.done >= pp.download.total) {
          return 'success';
        }
      } catch { /* ignore */ }
    }
    return 'running';
  }
  if (SUCCESS_STATUSES.has(task.status)) return 'success';
  if (PARTIAL_STATUSES.has(task.status)) return 'partial';
  if (FAILURE_STATUSES.has(task.status)) return 'failed';
  return 'unknown';
}

export function getTaskStatusLabel(task: Task) {
  const state = getTaskDisplayState(task);
  return (
    {
      running: '进行中',
      paused: '已暂停',
      success: '已完成',
      partial: '部分失败',
      failed: '失败',
      stale: '已过期',
      unknown: task.status,
    }[state] || task.status
  );
}

export function getTaskMessage(task: Task) {
  const msg = parseTaskMessage(task.payload) || task.error_msg || '';
  if (msg) return msg;
  if (task.status === 'COMPLETED' || task.status === 'SUCCESS') return '';
  return '暂无详细信息';
}

const SERVER_RESTART_ERROR = '服务重启导致任务中断，请点击重试恢复。';

export function isServerRestartError(task: Task): boolean {
  return task.error_msg === SERVER_RESTART_ERROR;
}

export function getTaskError(task: Task) {
  if (isServerRestartError(task)) {
    return SERVER_RESTART_ERROR;
  }
  if (isTaskStale(task)) {
    return '这个任务长时间没有更新，通常意味着浏览器或后台进程已经中断。建议重新发起。';
  }
  return task.error_msg || '';
}

export function getTaskDuration(task: Task): string {
  const ts = taskTimestamp(task);
  if (!ts) return '';

  const state = getTaskDisplayState(task);
  const now = Date.now();

  if (state === 'running') {
    const elapsed = now - ts;
    return `进行中 ${formatDurationMs(elapsed)}`;
  }

  const elapsed = now - ts;
  return formatDurationMs(elapsed) + '前';
}

function formatDurationMs(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  if (totalSec < 60) return `${totalSec}秒`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  if (min < 60) return sec > 0 ? `${min}分${sec}秒` : `${min}分`;
  const hr = Math.floor(min / 60);
  const remainMin = min % 60;
  return remainMin > 0 ? `${hr}小时${remainMin}分` : `${hr}小时`;
}
