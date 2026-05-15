import { memo, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, ChevronDown, FileText, Loader2, MinusCircle, RotateCw, Trash2, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useStore } from '@/store/useStore';
import {
  getTaskDisplayState,
  getTaskDuration,
  getTaskError,
  getTaskMessage,
  getTaskStatusLabel,
  getStageInfo,
  isServerRestartError,
  taskTypeLabel,
} from '@/lib/task-utils';
import { cancelTask, rerunTask, retryFailedSubtasks, setAutoRetry, deleteTask, recoverAwemeAndTranscribe, retryCreatorTranscribeCleanup } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import type { Task } from '@/lib/api';
import type { PipelineProgress, TaskStage } from '@/types';

type TaskSubtask = {
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

const EMPTY_SUBTASKS: TaskSubtask[] = [];

type TaskPayload = {
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
};

function formatDoneTotal(done: unknown, total: unknown) {
  const doneValue = typeof done === 'number' && Number.isFinite(done) ? done : null;
  const totalValue = typeof total === 'number' && Number.isFinite(total) ? total : null;
  const doneText = doneValue == null ? '--' : String(doneValue);
  const totalText = totalValue == null || totalValue <= 0 ? '--' : String(totalValue);
  return `${doneText}/${totalText}`;
}

function parsePayload(payload?: string): TaskPayload | null {
  if (!payload) return null;
  try {
    const parsed = JSON.parse(payload);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    return parsed as TaskPayload;
  } catch {
    return null;
  }
}

function resolveSubtaskErrorInfo(
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

function buildTaskCenterProgressLine(task: Task, parsed: TaskPayload | null) {
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

function stageLabel(stage: string) {
  const stageInfo = getStageInfo(stage as TaskStage);
  return stageInfo.label || stage || '';
}

function exportStatusLabel(status: unknown) {
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

function cleanupReasonLabel(reason: string) {
  const normalized = reason.trim();
  if (!normalized) return CLEANUP_REASON_LABELS.unknown;
  return CLEANUP_REASON_LABELS[normalized] ?? normalized;
}

function TaskCenterStageDots({ stage }: { stage: string }) {
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

function TaskCenterCleanupSummary({ parsed, taskId }: { parsed: TaskPayload | null; taskId: string }) {
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
    <div className="rounded-[var(--radius-card)] border border-border/60 bg-secondary/20 px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[12px] font-semibold text-foreground/80">清理汇总</div>
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
            'flex h-7 items-center gap-1 rounded-md px-2 text-[11px] font-medium transition-colors duration-200',
            isDisabled
              ? 'text-muted-foreground/70 cursor-not-allowed opacity-60'
              : 'text-primary hover:bg-primary/10',
          )}
          title={canRetry ? '重试删除失败的文件（安全白名单）' : '暂无可重试的失败项'}
        >
          {isRetrying ? <Loader2 className="size-3 animate-spin" aria-hidden="true" /> : <RotateCw className="size-3" aria-hidden="true" />}
          重试清理
        </button>
      </div>

      {(hasCleanupSummary || hasResultSummary) && (
        <p className="mt-1 text-[12px] text-muted-foreground">
          成功 {success} · 失败 {failed} · 共 {total}
        </p>
      )}

      {reasonCounts.length > 0 && (
        <div className={cn('mt-2 flex flex-wrap gap-1.5', !(hasCleanupSummary || hasResultSummary) && 'mt-1')}>
          {reasonCounts.map(({ label, count }) => (
            <span
              key={label}
              className="rounded-md border border-border/60 bg-background/60 px-2 py-1 text-[11px] text-foreground/70"
            >
              {label} × {count}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

interface TaskItemProps {
  task: Task;
  onRetry: (task: Task) => void;
  isExpanded: boolean;
  onToggleExpand: (taskId: string) => void;
}

export const TaskItem = memo(function TaskItem({ task, onRetry, isExpanded, onToggleExpand }: TaskItemProps) {
  const navigate = useNavigate();
  const state = getTaskDisplayState(task);
  const message = getTaskMessage(task);
  const error = getTaskError(task);
  const duration = getTaskDuration(task);
  const [subtasksExpanded, setSubtasksExpanded] = useState(false);
  const isRunning = state === 'running';
  const isPaused = state === 'paused';
  const isFailed = state === 'failed' || state === 'stale';
  const isServerRestart = isFailed && isServerRestartError(task);
  const isPartial = state === 'partial';
  const parsed = useMemo(() => parsePayload(task.payload), [task.payload]);
  const failedRetryableCount = useMemo(() => {
    if (!isFailed && !isPartial) return 0;
    const raw = parsed?.subtasks;
    if (!Array.isArray(raw)) return 0;
    let count = 0;
    for (const item of raw as TaskSubtask[]) {
      if (item && item.status === 'failed' && typeof item.video_path === 'string' && item.video_path.trim()) {
        count += 1;
      }
    }
    return count;
  }, [isFailed, isPartial, parsed]);
  const showTaskCenterProgress =
    task.task_type === 'pipeline' ||
    task.task_type === 'download' ||
    task.task_type === 'local_transcribe' ||
    task.task_type === 'creator_transcribe' ||
    task.task_type.startsWith('creator_sync_');
  const pp = parsed?.pipeline_progress;
  const shouldShowTaskCenterProgress = showTaskCenterProgress && !!pp;
  const taskCenterProgressLine = shouldShowTaskCenterProgress ? buildTaskCenterProgressLine(task, parsed) : '';
  const isR1TaskCenterRow = showTaskCenterProgress && !!pp;

  if (isR1TaskCenterRow) {
    const stage = pp?.stage ? String(pp.stage) : '';
    const stageText = stageLabel(stage);
    const missingCount = pp?.audit?.missing ?? (Array.isArray(parsed?.missing_items) ? parsed?.missing_items.length : 0);
    let downloadDone = pp?.download?.done ?? 0;
    const downloadTotal = pp?.download?.total ?? 0;

    // pipeline_progress.download.done 从 progress 字段估算，下载进行中时 progress 为 0
    // 优先使用 current_index（表示正在处理第几个视频），其次从消息文本解析
    if (downloadDone === 0 && isRunning) {
      const currentIndex = pp?.download?.current_index ?? 0;
      if (currentIndex > 0) {
        downloadDone = currentIndex;
      } else if (message) {
        const m = message.match(/正在下载\s*\(?\s*(\d+)\s*\/\s*(\d+)\s*\)?/);
        if (m) {
          downloadDone = parseInt(m[1], 10);
        }
      }
    }

    // 同理，转写阶段也从消息文本解析实际进度（格式: "正在转写 (2/5)" 或 "正在转写 2/5"）
    let transcribeDone = pp?.transcribe?.done ?? 0;
    const transcribeTotal = pp?.transcribe?.total ?? 0;
    if (transcribeDone === 0 && isRunning && message) {
      const m = message.match(/正在转写\s*\(?\s*(\d+)\s*\/\s*(\d+)\s*\)?/);
      if (m) {
        transcribeDone = parseInt(m[1], 10);
      }
    }

    const currentTitleRaw =
      stage === 'download'
        ? pp?.download && typeof pp.download.current_title === 'string'
          ? pp.download.current_title
          : ''
        : stage === 'transcribe'
          ? pp?.transcribe && typeof pp.transcribe.current_title === 'string'
            ? pp.transcribe.current_title
            : ''
          : '';
    const currentTitle = currentTitleRaw ? `当前：${currentTitleRaw.slice(0, 40)}` : '';

    const remaining =
      stage === 'transcribe' && transcribeTotal > 0
        ? Math.max(transcribeTotal - transcribeDone, 0)
        : downloadTotal > 0
          ? Math.max(downloadTotal - downloadDone, 0)
          : 0;
    const exportStatus = exportStatusLabel(pp?.export?.status);
    const transcribeAccountId = pp?.transcribe?.account_id;

    const subtitleParts = [
      pp?.download ? `下载 ${formatDoneTotal(downloadDone, downloadTotal)}` : '',
      pp?.transcribe ? `转写 ${formatDoneTotal(transcribeDone, transcribeTotal)}${transcribeAccountId ? ` [${transcribeAccountId}]` : ''}` : '',
      currentTitle,
      missingCount > 0 ? `缺失 ${missingCount}` : '',
      pp?.export ? `导出 ${exportStatus}` : '',
    ].filter(Boolean);

    const subtitle = subtitleParts.join(' · ') || message;
    const drawerId = `task-center-${task.task_id}`;
    const icon =
      state === 'running' ? (
        <Loader2 className="size-4 text-primary animate-spin" />
      ) : state === 'success' ? (
        <CheckCircle2 className="size-4 text-success" />
      ) : state === 'paused' ? (
        <MinusCircle className="size-4 text-warning" />
      ) : state === 'failed' || state === 'stale' ? (
        <XCircle className="size-4 text-destructive" />
      ) : (
        <Loader2 className="size-4 text-muted-foreground" />
      );

    return (
      <div className="overflow-hidden rounded-[var(--radius-card)] border border-border/60 bg-card apple-shadow-md">
        <button
          type="button"
          aria-expanded={isExpanded}
          aria-controls={drawerId}
          onClick={() => onToggleExpand(task.task_id)}
          className="group flex w-full items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-secondary/40"
        >
          <div className="relative flex size-9 shrink-0 items-center justify-center rounded-xl bg-secondary/70">
            {icon}
            {isRunning && <span className="absolute right-1.5 top-1.5 size-2 rounded-md bg-primary animate-pulse" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="truncate text-[13px] font-semibold text-foreground/85">{taskTypeLabel(task.task_type)}</span>
              {task.priority && task.priority > 0 && (
                <Badge className="shrink-0 text-[10px] bg-warning/10 text-warning">
                  优先级 {task.priority}
                </Badge>
              )}
            </div>
            <div className="mt-0.5 truncate text-[12px] text-muted-foreground">{subtitle}</div>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[12px] font-medium text-foreground/80">
              剩余 {remaining} 条
            </span>
            <TaskCenterStageDots stage={stage} />
            <span className="text-[12px] text-muted-foreground">{getTaskStatusLabel(task)}</span>
            <ChevronDown className={cn('size-4 text-muted-foreground transition-transform', isExpanded ? 'rotate-180' : '')} />
          </div>
        </button>

        {isExpanded && (
          <div id={drawerId} className="border-t border-border/60 px-4 pb-4 pt-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    tone={
                      state === 'running'
                        ? 'secondary'
                        : state === 'paused'
                          ? 'warning'
                          : state === 'success'
                            ? 'success'
                            : state === 'failed' || state === 'stale'
                              ? 'destructive'
                              : 'default'
                    }
                  >
                    {getTaskStatusLabel(task)}
                  </Badge>
                  {duration && <span className="text-[11px] text-muted-foreground tabular-nums">{duration}</span>}
                  <span className="text-[11px] text-muted-foreground">{stageText}</span>
                </div>
                <div className="mt-1 text-xs font-mono text-muted-foreground/50">{task.task_id}</div>
              </div>
              <TaskActions task={task} isRunning={isRunning} isPaused={isPaused} isFailed={isFailed} isPartial={isPartial} onRetry={onRetry} failedRetryableCount={failedRetryableCount} />
            </div>

            {(isRunning || isPaused) && (
              <div className="mt-3 text-xs text-muted-foreground">{message}</div>
            )}

            {isServerRestart && (
              <div className="mt-3 flex items-center gap-3 rounded-[var(--radius-card)] border border-amber-500/30 bg-amber-500/10 px-3 py-2.5">
                <span className="text-xs font-medium text-amber-600 dark:text-amber-400">服务重启导致任务中断</span>
                <button
                  onClick={() => onRetry(task)}
                  className="flex h-7 items-center gap-1 rounded-md bg-primary px-3 text-[11px] font-semibold text-primary-foreground hover:bg-primary/90"
                >
                  <RotateCw className="size-3" />
                  一键重试
                </button>
              </div>
            )}

            {error && !isServerRestart && (
              <div className="mt-3 rounded-[var(--radius-card)] border border-destructive/20 bg-destructive/10 p-3 text-xs leading-6 text-destructive whitespace-pre-wrap">
                {error}
              </div>
            )}

            {/* 清理汇总（仅转写任务有） */}
            <TaskCenterCleanupSummary parsed={parsed} taskId={task.task_id} />

            {/* 运行中：直接展示实时视频列表；已完成/失败：折叠显示 */}
            <TaskSubtasks
              task={task}
              isExpanded={isRunning || isPaused ? true : subtasksExpanded}
              onToggleExpand={() => setSubtasksExpanded((prev) => !prev)}
              showToggle={!(isRunning || isPaused)}
            />

            {/* 已完成的任务显示汇总统计 */}
            {!isRunning && <TaskStats task={task} />}

            {/* 已完成的任务显示最终消息 */}
            {!isRunning && !isPaused && <div className="mt-2 text-xs text-muted-foreground">{message}</div>}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-[var(--radius-card)] border border-border/60 bg-card p-4 apple-shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-foreground">{taskTypeLabel(task.task_type)}</span>
            <Badge
              tone={
                state === 'running'
                  ? 'secondary'
                  : state === 'paused'
                    ? 'warning'
                    : state === 'success'
                      ? 'success'
                      : state === 'failed' || state === 'stale'
                        ? 'destructive'
                        : 'default'
              }
            >
              {getTaskStatusLabel(task)}
            </Badge>
            {task.priority && task.priority > 0 && (
              <Badge className="text-[10px] bg-warning/10 text-warning">
                优先级 {task.priority}
              </Badge>
            )}
            {duration && <span className="text-[11px] text-muted-foreground tabular-nums">{duration}</span>}
          </div>
          <div className="mt-1 text-xs font-mono text-muted-foreground/50">{task.task_id}</div>
        </div>
        <TaskActions task={task} isRunning={isRunning} isPaused={isPaused} isFailed={isFailed} isPartial={isPartial} onRetry={onRetry} failedRetryableCount={failedRetryableCount} />
      </div>

      {(isRunning || isPaused) && (
        <div className="mt-3 space-y-2">
          {shouldShowTaskCenterProgress ? (
            <div className="space-y-1 text-xs">
              <div className="text-muted-foreground">{message}</div>
              <div className="text-muted-foreground tabular-nums">{taskCenterProgressLine}</div>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{message}</span>
                <span className="font-medium text-primary tabular-nums">{Math.round((task.progress || 0) * 100)}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="relative h-full rounded-full bg-primary transition-all duration-500 ease-out apple-progress-bar"
                  style={{ width: `${Math.max(2, (task.progress || 0) * 100)}%` }}
                />
              </div>
            </>
          )}
        </div>
      )}

      {!isRunning && <div className="mt-3 text-sm leading-6 text-muted-foreground">{message}</div>}

      {isServerRestart && (
        <div className="mt-3 flex items-center gap-3 rounded-[var(--radius-card)] border border-amber-500/30 bg-amber-500/10 px-3 py-2.5">
          <span className="text-xs font-medium text-amber-600 dark:text-amber-400">服务重启导致任务中断</span>
          <button
            onClick={() => onRetry(task)}
            className="flex h-7 items-center gap-1 rounded-md bg-primary px-3 text-[11px] font-semibold text-primary-foreground hover:bg-primary/90"
          >
            <RotateCw className="size-3" />
            一键重试
          </button>
        </div>
      )}

      {error && !isServerRestart && (
        <div className="mt-3 rounded-[var(--radius-card)] border border-destructive/20 bg-destructive/10 p-3 text-xs leading-6 text-destructive whitespace-pre-wrap">
          {error}
        </div>
      )}

      <TaskStats task={task} />
      <TaskSubtasks task={task} isExpanded={isExpanded} onToggleExpand={onToggleExpand} />
    </div>
  );
});

function TaskActions({
  task,
  isRunning,
  isPaused,
  isFailed,
  isPartial = false,
  onRetry,
  failedRetryableCount = 0,
  variant,
}: {
  task: Task;
  isRunning: boolean;
  isPaused: boolean;
  isFailed: boolean;
  isPartial?: boolean;
  onRetry: (task: Task) => void;
  failedRetryableCount?: number;
  variant?: 'macos';
}) {
  const autoRetryEnabled = !!task.auto_retry;
  const canStop = isRunning || isPaused;
  const [retryingFailed, setRetryingFailed] = useState(false);

  return (
    <div className={cn('mt-0.5 flex items-center gap-2', variant === 'macos' && 'gap-2')}>
      {isFailed && (
        <button
          onClick={() => onRetry(task)}
          className={cn(
            'flex h-8 items-center gap-1 rounded-md px-3 text-xs font-medium text-primary transition-colors duration-200 hover:bg-primary/10',
            variant === 'macos' &&
              'h-auto rounded-[8px] border-[0.5px] border-[#3C3C43]/[0.18] bg-white/40 px-3 py-1.5 text-[13px] font-semibold text-[#007AFF] hover:bg-white/60',
          )}
          title="重试（重新提交一个新任务）"
        >
          <RotateCw className="size-3.5" />
          重试
        </button>
      )}

      {(isFailed || isPartial) && failedRetryableCount > 0 && (
        <button
          disabled={retryingFailed}
          onClick={async () => {
            if (retryingFailed) return;
            try {
              setRetryingFailed(true);
              const data = await retryFailedSubtasks(task.task_id);
              const { fetchInitialTasks } = useStore.getState();
              await fetchInitialTasks();
              toast.success(`已派发新任务，仅重试 ${data.file_count} 个失败视频`);
            } catch {
              // interceptor already toasts
            } finally {
              setRetryingFailed(false);
            }
          }}
          className={cn(
            'flex h-8 items-center gap-1 rounded-md px-3 text-xs font-medium text-primary transition-colors duration-200 hover:bg-primary/10',
            variant === 'macos' &&
              'h-auto rounded-[8px] border-[0.5px] border-[#3C3C43]/[0.18] bg-white/40 px-3 py-1.5 text-[13px] font-semibold text-[#007AFF] hover:bg-white/60',
            retryingFailed ? 'cursor-not-allowed opacity-50' : '',
          )}
          title={`只针对失败视频派发新任务（共 ${failedRetryableCount} 个）`}
        >
          {retryingFailed ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCw className="size-3.5" />}
          只重试失败 ({failedRetryableCount})
        </button>
      )}

      {isPaused && (
        <button
          onClick={async () => {
            try {
              await rerunTask(task.task_id);
              const { fetchInitialTasks } = useStore.getState();
              await fetchInitialTasks();
              toast.success('任务已恢复运行');
            } catch {
              // interceptor already toasts
            }
          }}
          className={cn(
            'flex h-8 items-center gap-1 rounded-md px-3 text-xs font-medium text-primary transition-colors duration-200 hover:bg-primary/10',
            variant === 'macos' &&
              'h-auto rounded-[8px] border-[0.5px] border-[#3C3C43]/[0.18] bg-white/40 px-3 py-1.5 text-[13px] font-semibold text-[#007AFF] hover:bg-white/60',
          )}
          title="恢复此任务（继续使用同一任务ID）"
        >
          <RotateCw className="size-3.5" />
          恢复
        </button>
      )}

      {isFailed && (
        <button
          onClick={async () => {
            const next = !autoRetryEnabled;
            try {
              await setAutoRetry(task.task_id, next);
              const { fetchInitialTasks } = useStore.getState();
              await fetchInitialTasks();
              toast.success(next ? '自动重试已启用' : '自动重试已关闭');
            } catch {
              // interceptor already toasts
            }
          }}
          className={cn(
            'flex h-8 items-center rounded-md px-3 text-xs font-medium text-primary transition-colors duration-200 hover:bg-primary/10',
            variant === 'macos' &&
              'h-auto rounded-[8px] border-[0.5px] border-[#3C3C43]/[0.18] bg-white/40 px-3 py-1.5 text-[13px] font-semibold text-[#000]/70 hover:bg-white/60',
          )}
          title="失败/过期后自动重试"
        >
          自动重试: {autoRetryEnabled ? '开' : '关'}
        </button>
      )}

      {canStop && (
        <button
          onClick={async () => {
            try {
              await cancelTask(task.task_id);
              const { fetchInitialTasks } = useStore.getState();
              await fetchInitialTasks();
              toast.success('任务已停止');
            } catch {
              // interceptor already toasts
            }
          }}
          className={cn(
            'flex h-8 items-center rounded-md px-3 text-xs font-medium text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground',
            variant === 'macos' &&
              'h-auto rounded-[8px] border-[0.5px] border-[#3C3C43]/[0.18] bg-white/40 px-3 py-1.5 text-[13px] font-semibold text-[#3C3C43]/60 hover:bg-white/60',
          )}
          title="停止任务"
        >
          停止
        </button>
      )}

      {variant !== 'macos' && isRunning && <Loader2 className="size-4 animate-spin text-primary" />}
      {variant !== 'macos' && getTaskDisplayState(task) === 'success' && <CheckCircle2 className="size-4 text-success" />}
      <button
        onClick={async () => {
          try {
            await deleteTask(task.task_id);
            const { fetchInitialTasks } = useStore.getState();
            await fetchInitialTasks();
            toast.success('任务已删除');
          } catch {
            // interceptor already toasts
          }
        }}
        className={cn(
          'flex h-8 items-center gap-1 rounded-md px-3 text-xs font-medium text-destructive transition-colors duration-200 hover:bg-destructive/10',
          variant === 'macos' &&
            'ml-4 h-auto rounded-[8px] border-[0.5px] border-[#FF3B30]/20 bg-[#FF3B30]/[0.06] px-3 py-1.5 text-[13px] font-semibold text-[#FF3B30] hover:bg-[#FF3B30]/10',
        )}
        title={variant === 'macos' ? '删除记录（不可恢复）' : '删除任务（不可恢复）'}
      >
        <Trash2 className="size-3.5" />
        {variant === 'macos' ? '删除记录' : '删除'}
      </button>
    </div>
  );
}

function TaskStats({ task }: { task: Task }) {
  const parsed = parsePayload(task.payload);
  const summary = parsed?.result_summary as { success?: number; failed?: number; total?: number } | undefined;
  if (!summary || summary.total == null) return null;
  return (
    <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
      <span className="flex items-center gap-1">
        <CheckCircle2 className="size-3 text-success" />
        {summary.success || 0}
      </span>
      {summary.failed ? (
        <span className="flex items-center gap-1">
          <XCircle className="size-3 text-destructive" />
          {summary.failed}
        </span>
      ) : null}
      <span>共 {summary.total} 个</span>
    </div>
  );
}

function TaskSubtasks({
  task,
  isExpanded,
  onToggleExpand,
  showToggle = true,
}: {
  task: Task;
  isExpanded: boolean;
  onToggleExpand: (taskId: string) => void;
  showToggle?: boolean;
}) {
  const parsed = useMemo(() => parsePayload(task.payload), [task.payload]);
  const [retryingTask, setRetryingTask] = useState(false);
  const subtasks = useMemo(() => {
    const raw = parsed?.subtasks;
    if (!Array.isArray(raw)) return EMPTY_SUBTASKS;
    return raw as TaskSubtask[];
  }, [parsed]);
  const [recoveringAwemeId, setRecoveringAwemeId] = useState<string | null>(null);
  const creatorUidFromPayload =
    typeof parsed?.creator_uid === 'string'
      ? parsed.creator_uid
      : typeof parsed?.uid === 'string'
        ? parsed.uid
        : undefined;
  const missingItems = useMemo(() => {
    const raw = parsed?.missing_items;
    if (!Array.isArray(raw)) return [];
    return raw.filter((item) => item && typeof item === 'object' && !Array.isArray(item)) as Array<{
      aweme_id?: unknown;
      title?: unknown;
      reason?: unknown;
    }>;
  }, [parsed]);

  const enhancedSubtasks = useMemo(() => {
    if (!subtasks.length) return [];
    if (!missingItems.length && !creatorUidFromPayload) return subtasks;
    const byTitle = new Map<string, Array<{ awemeId: string; reason?: string }>>();
    for (const item of missingItems) {
      const title = typeof item.title === 'string' ? item.title : '';
      const awemeId = typeof item.aweme_id === 'string' ? item.aweme_id : '';
      const reason = typeof item.reason === 'string' ? item.reason : '';
      if (!title || !awemeId) continue;
      const list = byTitle.get(title) ?? [];
      list.push({ awemeId, reason: reason || undefined });
      byTitle.set(title, list);
    }

    const usedByTitle = new Map<string, number>();

    return subtasks.map((sub) => {
      if (sub.status !== 'manual_required') {
        return creatorUidFromPayload && !sub.creator_uid ? { ...sub, creator_uid: creatorUidFromPayload } : sub;
      }

      let awemeId = sub.aweme_id;
      let reason =
        typeof sub.reason === 'string' && sub.reason
          ? sub.reason
          : typeof sub.error === 'string' && sub.error
            ? sub.error
            : undefined;
      if (!awemeId && sub.title) {
        const list = byTitle.get(sub.title);
        if (list && list.length) {
          const used = usedByTitle.get(sub.title) ?? 0;
          const selected = list[Math.min(used, list.length - 1)];
          awemeId = selected?.awemeId;
          if (!reason && selected?.reason) reason = selected.reason;
          usedByTitle.set(sub.title, used + 1);
        }
      }

      return {
        ...sub,
        aweme_id: awemeId,
        creator_uid: sub.creator_uid ?? creatorUidFromPayload,
        reason,
      };
    });
  }, [creatorUidFromPayload, missingItems, subtasks]);

  if (subtasks.length === 0) return null;
  const completed = subtasks.filter((s) => s.status === 'completed').length;
  const skipped = subtasks.filter((s) => s.status === 'skipped').length;
  const failed = subtasks.filter((s) => s.status === 'failed').length;
  return (
    <div className="mt-3">
      {showToggle ? (
        <button
          onClick={() => onToggleExpand(task.task_id)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronDown className={cn('size-3.5 transition-transform', isExpanded ? 'rotate-180' : '')} />
          <FileText className="size-3" />
          详情 {completed}/{subtasks.length}
          {skipped > 0 && <span className="text-[10px] text-muted-foreground/60">(跳过 {skipped})</span>}
          {failed > 0 && <span className="text-[10px] text-destructive/70">(失败 {failed})</span>}
        </button>
      ) : (
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <CheckCircle2 className="size-3 text-success" />
            {completed}
          </span>
          {failed > 0 && (
            <span className="flex items-center gap-1">
              <XCircle className="size-3 text-destructive" />
              {failed}
            </span>
          )}
          <span>/ {subtasks.length}</span>
        </div>
      )}
      {isExpanded && (
        <div className="mt-2 space-y-1 max-h-48 overflow-y-auto rounded-[var(--radius-card)] border border-border/40 bg-muted/30 p-2">
          {enhancedSubtasks.map((sub, idx) => {
            const canRecover = sub.status === 'manual_required' && !!sub.creator_uid && !!sub.aweme_id;
            const isRecovering = !!sub.aweme_id && recoveringAwemeId === sub.aweme_id;
            const manualReason =
              sub.status === 'manual_required'
                ? typeof sub.reason === 'string' && sub.reason
                  ? sub.reason
                  : typeof sub.error === 'string' && sub.error
                    ? sub.error
                    : undefined
                : undefined;
            const isCorruptFile = manualReason === 'corrupt_file';
            const reasonLabel = isCorruptFile ? '文件异常' : '';
            const actionLabel = isCorruptFile ? '重下并转写' : '补齐并转写';
            const successToast = isCorruptFile ? '已创建重下并转写任务' : '已创建补齐任务';
            const actionTitle = isCorruptFile ? '创建重下并转写任务' : '创建补齐并转写任务';
            const shouldShowErrorText = !!sub.error && !(sub.status === 'manual_required' && sub.error === 'corrupt_file');
            const errorInfo = sub.status === 'failed' ? resolveSubtaskErrorInfo(sub) : null;
            return (
            <div
              key={idx}
              className="flex items-start gap-2 px-2 py-1.5 rounded-md text-xs"
              title={sub.error || ''}
            >
              {sub.status === 'completed' ? (
                <CheckCircle2 className="size-3.5 text-success shrink-0 mt-0.5" />
              ) : sub.status === 'skipped' ? (
                <MinusCircle className="size-3.5 text-muted-foreground shrink-0 mt-0.5" />
              ) : sub.status === 'pending' ? (
                <Loader2 className="size-3.5 text-primary shrink-0 mt-0.5 animate-spin" />
              ) : (
                <XCircle className="size-3.5 text-destructive shrink-0 mt-0.5" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-1.5">
                  <span
                    className={cn(
                      'block truncate',
                      sub.status === 'completed'
                        ? 'text-foreground/80'
                        : sub.status === 'skipped'
                          ? 'text-muted-foreground'
                          : sub.status === 'pending'
                            ? 'text-primary'
                            : 'text-destructive'
                    )}
                  >
                    {sub.title || '未命名'}
                  </span>
                  {reasonLabel && (
                    <span className="shrink-0 rounded-md bg-destructive/10 px-1.5 py-0.5 text-[10px] font-medium text-destructive">
                      {reasonLabel}
                    </span>
                  )}
                </div>
                {shouldShowErrorText && errorInfo ? (
                  <div className="mt-0.5 space-y-0.5 text-[10px] text-destructive/80">
                    <div>{errorInfo.label}</div>
                    {errorInfo.suggestion ? <div className="text-muted-foreground">建议：{errorInfo.suggestion}</div> : null}
                    {errorInfo.action ? (
                      <button
                        disabled={retryingTask}
                        onClick={async () => {
                          if (errorInfo.action?.kind === 'open_settings') {
                            navigate('/settings');
                            return;
                          }
                          if (retryingTask) return;
                          try {
                            setRetryingTask(true);
                            await rerunTask(task.task_id);
                            const { fetchInitialTasks } = useStore.getState();
                            await fetchInitialTasks();
                            toast.success('已重新提交任务');
                          } catch {
                          } finally {
                            setRetryingTask(false);
                          }
                        }}
                        className={cn(
                          'mt-1 inline-flex h-7 items-center rounded-md px-2 text-[11px] font-medium text-primary transition-colors duration-200 hover:bg-primary/10',
                          retryingTask ? 'cursor-not-allowed opacity-50' : ''
                        )}
                      >
                        {errorInfo.action.label}
                      </button>
                    ) : null}
                  </div>
                ) : shouldShowErrorText ? (
                  <span className="block truncate text-[10px] text-destructive/80 mt-0.5">{sub.error}</span>
                ) : null}
              </div>
              {sub.status === 'manual_required' && (
                <button
                  disabled={!canRecover || isRecovering}
                  onClick={async () => {
                    const creatorUid = sub.creator_uid || creatorUidFromPayload;
                    const awemeId = sub.aweme_id;
                    if (!creatorUid || !awemeId) {
                      toast.error('缺少补齐所需参数（creator_uid / aweme_id）');
                      return;
                    }
                    try {
                      setRecoveringAwemeId(awemeId);
                      await recoverAwemeAndTranscribe(creatorUid, awemeId, sub.title || '');
                      const { fetchInitialTasks } = useStore.getState();
                      await fetchInitialTasks();
                      toast.success(successToast);
                    } catch {
                      // interceptor already toasts
                    } finally {
                      setRecoveringAwemeId(null);
                    }
                  }}
                  className={cn(
                    'flex h-7 items-center gap-1 rounded-md px-2 text-[11px] font-medium text-primary transition-colors duration-200',
                    canRecover && !isRecovering ? 'hover:bg-primary/10' : 'cursor-not-allowed opacity-50'
                  )}
                  title={canRecover ? actionTitle : '缺少 aweme_id 或 creator_uid，无法创建补齐任务'}
                >
                  {isRecovering ? <Loader2 className="size-3 animate-spin" /> : <RotateCw className="size-3" />}
                  {actionLabel}
                </button>
              )}
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
