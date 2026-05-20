import { useState } from 'react';
import { Loader2, RotateCw } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useStore } from '@/store/useStore';
import { retryCreatorTranscribeCleanup } from '@/lib/api';
import type { Task } from '@/lib/api';
import { getStageInfo } from '@/lib/task-utils';
import type { PipelineProgress, TaskStage } from '@/types';

export type TaskSubtask = {
  title: string;
  status: string;
  error?: string;
  error_type?: string;
  attempts?: number;
  reason?: string;
  aweme_id?: string;
  creator_uid?: string;
  video_path?: string;
};

export const EMPTY_SUBTASKS: TaskSubtask[] = [];

export type TaskPayload = {
  msg?: string;
  stage?: string;
  pipeline_progress?: PipelineProgress;
  subtasks?: unknown;
  missing_items?: unknown;
  result_summary?: unknown;
  cleanup_deleted_count?: unknown;
  cleanup_failed_count?: unknown;
  cleanup_failed_paths?: unknown;
  cleanup_retry_at?: unknown;
  uid?: string;
  creator_uid?: string;
  url?: string;
  file_paths?: string[];
};

export function formatDoneTotal(done: unknown, total: unknown) {
  const doneValue = typeof done === 'number' && Number.isFinite(done) ? done : null;
  const totalValue = typeof total === 'number' && Number.isFinite(total) ? total : null;
  const doneText = doneValue == null ? '--' : String(doneValue);
  const totalText = totalValue == null || totalValue <= 0 ? '--' : String(totalValue);
  return `${doneText}/${totalText}`;
}

export function parsePayload(payload?: string): TaskPayload | null {
  if (!payload) return null;
  try {
    const parsed = JSON.parse(payload);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    return parsed as TaskPayload;
  } catch {
    return null;
  }
}

export function resolveSubtaskErrorInfo(
  sub: TaskSubtask
): { label: string; suggestion?: string; action?: { label: string; kind: 'retry_task' | 'open_settings' } } | null {
  const rawType = typeof sub.error_type === 'string' ? sub.error_type.trim().toLowerCase() : '';
  const error = typeof sub.error === 'string' ? sub.error : '';
  const inferredType = !rawType && error.includes(':') ? (error.split(':')[0] || '').trim().toLowerCase() : '';
  const type = rawType || inferredType;

  const mapping: Record<string, { label: string; suggestion?: string; action?: { label: string; kind: 'retry_task' | 'open_settings' } }> =
    {
      timeout: { label: '网络超时', suggestion: '重试或检查网络', action: { label: '重试任务', kind: 'retry_task' } },
      network: { label: '网络异常', suggestion: '检查网络或代理后重试', action: { label: '重试任务', kind: 'retry_task' } },
      quota: { label: '额度不足/限流', suggestion: '更换账号或稍后重试', action: { label: '去设置', kind: 'open_settings' } },
      auth: { label: '鉴权失败', suggestion: '检查账号/Cookie 状态', action: { label: '去设置', kind: 'open_settings' } },
    file_not_found: { label: '文件不存在', suggestion: '确认文件路径与权限' },
    permission: { label: '权限不足', suggestion: '检查文件权限或运行权限' },
    validation: { label: '参数错误', suggestion: '检查输入参数或文件格式' },
    cancelled: { label: '已取消', suggestion: '重新发起任务' },
    unknown: { label: '未知错误' },
  };

  if (!type) return error ? { label: '失败', suggestion: error } : null;
  return mapping[type] || { label: type.toUpperCase(), suggestion: error || undefined };
}

export function buildTaskCenterProgressLine(task: Task, parsed: TaskPayload | null) {
  const pp = parsed?.pipeline_progress;
  const listDone = pp?.list?.done;
  const listTotal = pp?.list?.total;
  const listOk =
    typeof listDone === 'number' && typeof listTotal === 'number' && listTotal > 0 && listDone >= listTotal;

  const missingFromPayload = Array.isArray(parsed?.missing_items) ? parsed?.missing_items.length : 0;
  const auditMissing = pp?.audit?.missing ?? missingFromPayload;

  const downloadDone = pp?.download?.done;
  const downloadTotal = pp?.download?.total;
  const transcribeDone = pp?.transcribe?.done;
  const transcribeTotal = pp?.transcribe?.total;
  const exportPp = pp?.export;
  const exportDone = exportPp?.done ?? (task.status === 'COMPLETED' ? 1 : 0);
  const exportTotal = exportPp?.total ?? 1;
  const exportFile = exportPp?.file ?? null;
  const exportStatus = exportPp?.status ?? null;

  const parts = [
    `列表 ${formatDoneTotal(listDone, listTotal)}${listOk ? ' ✓' : ''}`,
    `对账 缺 ${auditMissing}`,
    `下载 ${formatDoneTotal(downloadDone, downloadTotal)}`,
    `转写 ${formatDoneTotal(transcribeDone, transcribeTotal)}`,
    `导出 ${formatDoneTotal(exportDone, exportTotal)}`,
  ];

  const meta = [exportFile ? String(exportFile) : '', exportStatus != null ? String(exportStatus) : '']
    .filter(Boolean)
    .join(' ');
  if (meta) parts.push(meta);
  return parts.join(' ');
}

export function stageLabel(stage: string) {
  const stageInfo = getStageInfo(stage as TaskStage);
  return stageInfo.label || stage || '';
}

export function exportStatusLabel(status: unknown) {
  const s = status == null ? '' : String(status);
  if (!s || s === 'pending') return '准备导出';
  if (s === 'writing') return '写入中';
  if (s === 'done') return '完成';
  if (s === 'failed') return '失败';
  if (s === 'polling') return '准备导出';
  return s;
}

const CLEANUP_REASON_LABELS: Record<string, string> = {
  corrupt_file: '文件异常',
  http_403: '403 无权限',
  forbidden: '403 无权限',
  removed: '已删除',
  deleted: '已删除',
  not_found: '未找到',
  permission_denied: '无权限',
  path_outside_root: '路径越界',
  private: '已设为私密',
  rate_limited: '触发限流',
  timeout: '超时',
  unknown: '未知原因',
};

export function cleanupReasonLabel(reason: string) {
  const normalized = reason.trim();
  if (!normalized) return CLEANUP_REASON_LABELS.unknown;
  return CLEANUP_REASON_LABELS[normalized] ?? normalized;
}

export function TaskCenterStageDots({ stage }: { stage: string }) {
  const mapping: Record<string, number> = {
    downloading: 0,
    uploading: 1,
    transcribing: 1,
    exporting: 2,
    completed: 2,
  };
  const idx = mapping[stage] ?? 0;
  return (
    <span className="flex items-center gap-1" aria-label="阶段：下载 / 转写 / 导出">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            i <= idx ? 'bg-primary' : 'bg-[#3C3C43]/[0.18]',
          )}
        />
      ))}
    </span>
  );
}

export function TaskCenterCleanupSummary({ parsed, taskId }: { parsed: TaskPayload | null; taskId: string }) {
  const [isRetrying, setIsRetrying] = useState(false);

  const cleanupDeletedRaw = parsed?.cleanup_deleted_count;
  const cleanupFailedRaw = parsed?.cleanup_failed_count;

  const cleanupDeletedCount =
    typeof cleanupDeletedRaw === 'number' ? cleanupDeletedRaw : typeof cleanupDeletedRaw === 'string' ? Number(cleanupDeletedRaw) : null;
  const cleanupFailedCount =
    typeof cleanupFailedRaw === 'number' ? cleanupFailedRaw : typeof cleanupFailedRaw === 'string' ? Number(cleanupFailedRaw) : null;

  const summary = parsed?.result_summary as { success?: number; failed?: number; total?: number } | undefined;
  const hasCleanupSummary = cleanupDeletedCount != null || cleanupFailedCount != null;
  const hasResultSummary = !!summary && summary.total != null;

  const reasonCounts = (() => {
    const counts = new Map<string, number>();

    const cleanupFailedPaths = parsed?.cleanup_failed_paths;
    if (Array.isArray(cleanupFailedPaths)) {
      for (const raw of cleanupFailedPaths) {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue;
        const reason = typeof (raw as { reason?: unknown }).reason === 'string' ? String((raw as { reason?: unknown }).reason) : '';
        if (!reason) continue;
        const label = cleanupReasonLabel(reason);
        counts.set(label, (counts.get(label) ?? 0) + 1);
      }
    } else if (Array.isArray(parsed?.missing_items)) {
      for (const raw of parsed.missing_items) {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue;
        const reason = typeof (raw as { reason?: unknown }).reason === 'string' ? String((raw as { reason?: unknown }).reason) : '';
        if (!reason) continue;
        const label = cleanupReasonLabel(reason);
        counts.set(label, (counts.get(label) ?? 0) + 1);
      }
    }

    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([label, count]) => ({ label, count }));
  })();

  if (!hasCleanupSummary && !hasResultSummary && reasonCounts.length === 0) return null;

  const success = (cleanupDeletedCount ?? (summary?.success ?? 0)) || 0;
  const failed = (cleanupFailedCount ?? (summary?.failed ?? 0)) || 0;
  const total = (hasResultSummary ? summary?.total : null) ?? success + failed;

  const canRetry = (cleanupFailedCount ?? 0) > 0;
  const isDisabled = !canRetry || isRetrying;

  return (
    <div className="rounded-[var(--radius-card)] border border-white/[0.03] bg-white/[0.015] px-4 py-3.5 mt-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[12px] font-semibold text-[var(--color-bone)]">清理汇总</div>
        <button
          type="button"
          disabled={isDisabled}
          onClick={async () => {
            if (!canRetry || isRetrying) return;
            setIsRetrying(true);
            try {
              const data = await retryCreatorTranscribeCleanup(taskId);
              const deletedCount = Number(data.deleted_count || 0);
              const failedCount = Number(data.failed_count || 0);
              if (failedCount > 0) {
                toast.success(`清理已重试：本次删除 ${deletedCount} 个，仍失败 ${failedCount} 个`);
              } else {
                toast.success(`清理已完成：本次删除 ${deletedCount} 个`);
              }
              const { fetchInitialTasks } = useStore.getState();
              await fetchInitialTasks();
            } catch {
              void 0;
            } finally {
              setIsRetrying(false);
            }
          }}
          className={cn(
            'flex h-7 items-center gap-1 px-2.5 text-[11.5px] font-semibold transition-all duration-200 border rounded-lg',
            isDisabled
              ? 'text-muted-foreground/40 cursor-not-allowed opacity-50 border-transparent bg-transparent'
              : 'text-[var(--color-rust)] border-[var(--color-rust)]/20 hover:border-[var(--color-rust)]/35 hover:bg-[var(--color-rust)]/10',
          )}
          title={canRetry ? '重试删除失败的文件（安全白名单）' : '暂无可重试的失败项'}
        >
          {isRetrying ? <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> : <RotateCw className="size-3.5" aria-hidden="true" />}
          重试清理
        </button>
      </div>

      {(hasCleanupSummary || hasResultSummary) && (
        <p className="mt-1.5 text-[12px] text-[var(--color-ash)] font-medium">
          成功 {success} · 失败 {failed} · 共 {total}
        </p>
      )}

      {reasonCounts.length > 0 && (
        <div className={cn('mt-2.5 flex flex-wrap gap-1.5', !(hasCleanupSummary || hasResultSummary) && 'mt-1.5')}>
          {reasonCounts.map(({ label, count }) => (
            <span
              key={label}
              className="rounded-md border border-white/[0.03] bg-white/5 px-2 py-0.5 text-[11px] text-[var(--color-smoke)] font-medium"
            >
              {label} × {count}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
