import { useState, useMemo, useEffect, useRef, type ReactNode } from 'react';
import { useStore } from '@/store/useStore';
import { useTaskActions } from '@/hooks/useTaskActions';
import {
  getTaskDisplayState,
  sortTasks,
  filterTasksByCategory,
  getTaskMessage,
  getTaskError,
  type TaskFilterCategory,
} from '@/lib/task-utils';
import type { Task } from '@/lib/api';
import {
  Loader2,
  CheckCircle2,
  AlertTriangle,
  RotateCw,
  Trash2,
  X,
  ListTodo,
  Square,
  Pause,
  Play,
  Info,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';

function parsePayload(payload?: string): Record<string, unknown> | null {
  if (!payload) return null;
  try {
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

const ERROR_LABELS: Record<string, string> = {
  timeout: '网络超时',
  network: '网络异常',
  quota: '额度不足',
  auth: '鉴权失败',
  file_not_found: '文件不存在',
  permission: '权限不足',
  validation: '参数错误',
  cancelled: '已取消',
  unknown: '未知错误',
};

function classifySubtaskError(sub: { error_type?: string; error?: string }): string | null {
  const rawType = typeof sub?.error_type === 'string' ? sub.error_type.trim().toLowerCase() : '';
  const error = typeof sub?.error === 'string' ? sub.error : '';
  const inferred = !rawType && error.includes(':') ? (error.split(':')[0] || '').trim().toLowerCase() : '';
  const type = rawType || inferred;
  if (!type) return null;
  return ERROR_LABELS[type] || type.toUpperCase();
}

function getTaskTitle(task: Task): string {
  const p = parsePayload(task.payload);
  if (p && typeof p.creator_name === 'string') return `同步: ${p.creator_name}`;
  if (p && typeof p.uid === 'string') return `同步创作者: ${String(p.uid).slice(0, 8)}`;

  switch (task.task_type) {
    case 'creator_sync_full':
    case 'creator_sync_incremental':
      return '同步创作者内容';
    case 'pipeline':
      return '下载 + 转写';
    case 'local_transcribe':
      return '本地媒体转写';
    case 'download':
      return '批量下载';
    case 'transcribe':
    case 'creator_transcribe':
      return '语音转写';
    default:
      return (p && typeof p.msg === 'string' && p.msg) || task.task_type || '未命名任务';
  }
}

const FILTER_TABS: { key: TaskFilterCategory; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'download', label: '下载' },
  { key: 'transcribe', label: '转写' },
  { key: 'sync', label: '同步' },
];

const STATE_LABEL: Record<string, string> = {
  running: '进行中',
  paused: '已暂停',
  success: '已完成',
  partial: '部分失败',
  failed: '失败',
  stale: '已中断',
  unknown: '未知',
};

interface TaskIslandProps {
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
}

function ActionBtn({
  onClick,
  title,
  variant = 'default',
  disabled,
  children,
}: {
  onClick: () => void;
  title?: string;
  variant?: 'default' | 'danger' | 'primary' | 'warn';
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      disabled={disabled}
      title={title}
      className={cn(
        'ui-press inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[12px] font-medium border cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed',
        variant === 'default' &&
          'bg-black/[0.03] dark:bg-white/[0.04] border-black/[0.06] dark:border-white/[0.08] text-[var(--color-bone)] hover:bg-black/[0.06] dark:hover:bg-white/[0.08]',
        variant === 'primary' &&
          'bg-[rgba(0,113,227,0.10)] border-[rgba(0,113,227,0.25)] text-[var(--color-rust)] hover:bg-[rgba(0,113,227,0.16)]',
        variant === 'warn' &&
          'bg-[rgba(245,158,11,0.10)] border-[rgba(245,158,11,0.25)] text-amber-700 dark:text-amber-400 hover:bg-[rgba(245,158,11,0.16)]',
        variant === 'danger' &&
          'bg-[rgba(239,68,68,0.08)] border-[rgba(239,68,68,0.22)] text-[var(--color-iron)] hover:bg-[rgba(239,68,68,0.14)]',
      )}
    >
      {children}
    </button>
  );
}

type FlashKind = 'ok' | 'err';

export function TaskIsland({ isOpen, onToggle, onClose }: TaskIslandProps) {
  const [filter, setFilter] = useState<TaskFilterCategory>('all');
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const [flashMap, setFlashMap] = useState<Record<string, FlashKind>>({});
  const [countBump, setCountBump] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const prevStatusRef = useRef<Map<string, string>>(new Map());
  const prevActiveCountRef = useRef(0);

  const rawTasks = useStore((state) => state.tasks);
  const fetchInitialTasks = useStore((state) => state.fetchInitialTasks);
  const { handleClearHistory, handleRetry, handlePause, handleResume, handleCancel, handleDelete } = useTaskActions();

  useEffect(() => {
    fetchInitialTasks();
  }, [fetchInitialTasks]);

  // Escape closes panel
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  const withBusy = async (taskId: string, fn: () => Promise<void>) => {
    setBusyIds((prev) => new Set(prev).add(taskId));
    try {
      await fn();
    } finally {
      setBusyIds((prev) => {
        const next = new Set(prev);
        next.delete(taskId);
        return next;
      });
    }
  };

  const activeTasks = useMemo(() => {
    return rawTasks.filter((t) => {
      const s = getTaskDisplayState(t);
      return s === 'running' || s === 'paused';
    });
  }, [rawTasks]);

  const failedCount = useMemo(() => {
    return rawTasks.filter((t) => {
      const s = getTaskDisplayState(t);
      return s === 'failed' || s === 'stale' || s === 'partial';
    }).length;
  }, [rawTasks]);

  const overallProgress = useMemo(() => {
    if (activeTasks.length === 0) return 0;
    const total = activeTasks.reduce((acc, t) => acc + (t.progress || 0), 0);
    return Math.round((total / activeTasks.length) * 100);
  }, [activeTasks]);

  const sortedTasks = useMemo(() => sortTasks([...rawTasks]), [rawTasks]);
  const filteredTasks = useMemo(() => filterTasksByCategory(sortedTasks, filter), [sortedTasks, filter]);

  const hasNonRunning = useMemo(() => {
    return sortedTasks.some((t) => {
      const s = getTaskDisplayState(t);
      return s !== 'running' && s !== 'paused';
    });
  }, [sortedTasks]);

  const radius = 9;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (overallProgress / 100) * circumference;
  const [fabFlash, setFabFlash] = useState(false);

  // 任务状态变化 → 卡片高亮；运行数变化 → 角标 bump
  useEffect(() => {
    const prev = prevStatusRef.current;
    const nextFlash: Record<string, FlashKind> = {};
    let hasFlash = false;
    for (const task of rawTasks) {
      const state = getTaskDisplayState(task);
      const old = prev.get(task.task_id);
      if (old && old !== state) {
        if (state === 'success') {
          nextFlash[task.task_id] = 'ok';
          hasFlash = true;
        } else if (state === 'failed' || state === 'stale' || state === 'partial') {
          nextFlash[task.task_id] = 'err';
          hasFlash = true;
        }
      }
      prev.set(task.task_id, state);
    }
    // prune removed tasks
    for (const id of [...prev.keys()]) {
      if (!rawTasks.some((t) => t.task_id === id)) prev.delete(id);
    }
    if (hasFlash) {
      setFlashMap((m) => ({ ...m, ...nextFlash }));
      const t = window.setTimeout(() => {
        setFlashMap((m) => {
          const copy = { ...m };
          for (const id of Object.keys(nextFlash)) delete copy[id];
          return copy;
        });
      }, 900);
      return () => window.clearTimeout(t);
    }
  }, [rawTasks]);

  useEffect(() => {
    if (prevActiveCountRef.current !== activeTasks.length) {
      if (activeTasks.length > 0) {
        setCountBump(true);
        const t = window.setTimeout(() => setCountBump(false), 320);
        prevActiveCountRef.current = activeTasks.length;
        return () => window.clearTimeout(t);
      }
      if (prevActiveCountRef.current > 0 && activeTasks.length === 0 && failedCount === 0) {
        setFabFlash(true);
        const t = window.setTimeout(() => setFabFlash(false), 650);
        prevActiveCountRef.current = 0;
        return () => window.clearTimeout(t);
      }
      prevActiveCountRef.current = activeTasks.length;
    }
  }, [activeTasks.length, failedCount]);

  return (
    <>
      {/* 唯一入口：状态球。有任务/失败时才显眼；空闲时收成淡图标，点开才是完整任务面板。 */}
      <button
        ref={buttonRef}
        onClick={onToggle}
        className={cn(
          'fixed bottom-6 right-6 z-40 flex items-center justify-center cursor-pointer select-none outline-none ui-press',
          'transition-[opacity,transform,box-shadow,border-color,background-color] duration-300 ease-out',
          isOpen && 'pointer-events-none opacity-0 scale-90 translate-y-1',
          fabFlash && 'ui-task-fab-done',
          activeTasks.length > 0
            ? 'h-11 px-4 rounded-full gap-2.5 bg-[var(--color-paper)] border border-black/[0.08] dark:border-white/10 shadow-[0_12px_40px_rgba(0,0,0,0.28)] hover:border-[var(--color-rust)]/40 hover:scale-[1.03] text-[var(--color-bone)] ui-task-fab-active'
            : failedCount > 0
              ? 'h-11 w-11 rounded-full bg-[rgba(239,68,68,0.12)] border border-red-500/25 shadow-[0_8px_24px_rgba(239,68,68,0.15)] hover:border-red-500/40 hover:scale-[1.04] text-red-400'
              : 'h-10 w-10 rounded-full bg-[var(--color-paper)]/70 backdrop-blur-md border border-black/[0.05] dark:border-white/10 shadow-sm text-[var(--color-smoke)] hover:text-[var(--color-bone)] hover:border-black/[0.1] hover:scale-105 opacity-70 hover:opacity-100',
        )}
        title={
          activeTasks.length > 0
            ? `${activeTasks.length} 项进行中 · 打开任务`
            : failedCount > 0
              ? `${failedCount} 项需处理 · 打开任务`
              : '打开任务 (⌘`)'
        }
        aria-label="打开任务"
      >
        {activeTasks.length > 0 ? (
          <>
            <div className="relative flex size-5 items-center justify-center shrink-0">
              <svg className="absolute inset-0 size-full -rotate-90" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r={radius} fill="none" stroke="rgba(128,128,128,0.2)" strokeWidth="2" />
                <circle
                  cx="12"
                  cy="12"
                  r={radius}
                  fill="none"
                  stroke="var(--color-rust)"
                  strokeWidth="2.2"
                  strokeDasharray={circumference}
                  strokeDashoffset={strokeDashoffset}
                  strokeLinecap="round"
                  className="transition-[stroke-dashoffset] duration-500 ease-out"
                />
              </svg>
              <span className="font-mono text-[9px] font-bold text-[var(--color-rust)]">{activeTasks.length}</span>
            </div>
            <span className="text-[12px] font-semibold tabular-nums tracking-wide">{overallProgress}%</span>
          </>
        ) : failedCount > 0 ? (
          <div className="relative">
            <AlertTriangle className="size-4" strokeWidth={2.2} />
            <span className="absolute -top-1 -right-1 size-2 rounded-full bg-red-500 animate-pulse" />
          </div>
        ) : (
          <ListTodo className="size-4" strokeWidth={1.8} />
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <>
            {/* Scrim */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="fixed inset-0 z-40 bg-black/25 backdrop-blur-[2px]"
              onClick={onClose}
            />

            {/* Full-height task center */}
            <motion.aside
              ref={panelRef}
              initial={{ x: 36, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 28, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 420, damping: 36, mass: 0.85 }}
              className="fixed top-0 right-0 bottom-0 z-50 w-full max-w-[440px] bg-[var(--color-paper)] border-l border-[var(--color-hairline)] shadow-[-16px_0_48px_rgba(0,0,0,0.2)] flex flex-col"
            >
              {/* Header */}
              <div className="flex items-start justify-between px-5 pt-5 pb-4 border-b border-[var(--color-hairline)] flex-shrink-0">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="text-[17px] font-semibold text-[var(--color-bone)]">任务</h2>
                    {activeTasks.length > 0 && (
                      <span
                        className={cn(
                          'px-2 py-0.5 rounded-md bg-[var(--color-rust)]/10 text-[11px] text-[var(--color-rust)] font-semibold tabular-nums',
                          countBump && 'ui-count-bump',
                        )}
                      >
                        {activeTasks.length} 运行中
                      </span>
                    )}
                    {failedCount > 0 && (
                      <span className="px-2 py-0.5 rounded-md bg-[var(--color-iron)]/10 text-[11px] text-[var(--color-iron)] font-semibold tabular-nums">
                        {failedCount} 需处理
                      </span>
                    )}
                  </div>
                  <p className="text-[12px] text-[var(--color-ash)] mt-1.5 leading-relaxed">
                    进度、失败与操作都在这里。暂停后恢复会从头执行，不是断点续传。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 text-[var(--color-smoke)] hover:text-[var(--color-bone)] transition-colors cursor-pointer"
                  title="关闭 (Esc)"
                >
                  <X className="size-4" />
                </button>
              </div>

              {/* Filters + clear */}
              <div className="px-5 py-3 flex items-center justify-between gap-3 border-b border-[var(--color-hairline)] flex-shrink-0">
                <div className="flex items-center p-0.5 rounded-lg bg-black/[0.03] dark:bg-white/[0.04] gap-0.5 flex-wrap">
                  {FILTER_TABS.map((tab) => (
                    <button
                      key={tab.key}
                      type="button"
                      onClick={() => setFilter(tab.key)}
                      data-active={filter === tab.key}
                      className={cn(
                        'ui-seg ui-press px-2.5 py-1.5 text-[12px] font-medium rounded-md cursor-pointer',
                        filter === tab.key
                          ? 'bg-[var(--color-paper)] text-[var(--color-rust)] shadow-sm'
                          : 'text-[var(--color-smoke)] hover:text-[var(--color-bone)]',
                      )}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
                {hasNonRunning && (
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm('清除所有已结束的历史任务记录？进行中的任务不受影响。')) {
                        void handleClearHistory();
                      }
                    }}
                    className="ui-press text-[12px] font-medium text-[var(--color-iron)] hover:underline cursor-pointer shrink-0"
                  >
                    清除历史
                  </button>
                )}
              </div>

              {/* List */}
              <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2.5">
                {filteredTasks.length === 0 ? (
                  <div className="ui-pop-enter py-24 text-center px-6">
                    <ListTodo className="size-8 mx-auto text-[var(--color-smoke)] opacity-40 mb-3" />
                    <div className="text-[14px] font-medium text-[var(--color-smoke)]">暂无任务</div>
                    <div className="text-[12px] text-[var(--color-ash)] mt-1">
                      在内容库发起同步、下载或转写后会出现在这里
                    </div>
                  </div>
                ) : (
                  filteredTasks.map((task, index) => {
                    const state = getTaskDisplayState(task);
                    const isRunning = state === 'running';
                    const isPaused = state === 'paused';
                    const isFailed = state === 'failed' || state === 'stale';
                    const isPartial = state === 'partial';
                    const isSuccess = state === 'success';
                    const pct = Math.round((task.progress || 0) * 100);
                    const title = getTaskTitle(task);
                    const busy = busyIds.has(task.task_id);
                    const err = getTaskError(task);
                    const flash = flashMap[task.task_id];

                    const parsed = parsePayload(task.payload);
                    const subtasks = Array.isArray(parsed?.subtasks)
                      ? (parsed!.subtasks as Array<{
                          title?: string;
                          status?: string;
                          error?: string;
                          error_type?: string;
                          video_path?: string;
                        }>)
                      : [];
                    const ppFiles = (() => {
                      const pp = parsed?.pipeline_progress as
                        { files?: Array<{ title?: string; status?: string; stage?: string }> } | undefined;
                      return Array.isArray(pp?.files) ? pp!.files! : [];
                    })();
                    const fileRows = isRunning && ppFiles.length > 0 ? ppFiles : subtasks;
                    const showFileRows = fileRows.length > 0;

                    return (
                      <motion.div
                        key={task.task_id}
                        layout
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{
                          duration: 0.22,
                          delay: Math.min(index * 0.03, 0.18),
                          layout: { type: 'spring', stiffness: 420, damping: 34 },
                        }}
                        className={cn(
                          'ui-task-card rounded-xl border p-3.5',
                          isRunning || isPaused
                            ? 'bg-black/[0.02] dark:bg-white/[0.03] border-[var(--color-hairline-strong)]'
                            : isFailed || isPartial
                              ? 'bg-[rgba(239,68,68,0.03)] border-[rgba(239,68,68,0.15)]'
                              : isSuccess
                                ? 'bg-[rgba(16,185,129,0.04)] border-[rgba(16,185,129,0.12)]'
                                : 'bg-transparent border-[var(--color-hairline)]',
                          flash === 'ok' && 'ui-task-card-ok',
                          flash === 'err' && 'ui-task-card-err',
                        )}
                      >
                        <div className="flex items-start gap-3">
                          <div className="mt-0.5 shrink-0">
                            {busy || isRunning ? (
                              <Loader2
                                className={cn('size-4 text-[var(--color-rust)]', (busy || isRunning) && 'animate-spin')}
                                strokeWidth={2.2}
                              />
                            ) : isPaused ? (
                              <Pause className="size-4 text-amber-500" strokeWidth={2.2} />
                            ) : isFailed ? (
                              <AlertTriangle className="size-4 text-[var(--color-iron)]" strokeWidth={2.2} />
                            ) : isPartial ? (
                              <AlertTriangle className="size-4 text-amber-500" strokeWidth={2.2} />
                            ) : isSuccess ? (
                              <CheckCircle2
                                className={cn('size-4 text-[var(--color-patina)]', flash === 'ok' && 'ui-check-pop')}
                                strokeWidth={2}
                              />
                            ) : (
                              <div className="size-2.5 rounded-full bg-black/20 dark:bg-white/20 mt-1" />
                            )}
                          </div>

                          <div className="min-w-0 flex-1">
                            <div className="flex items-start justify-between gap-2">
                              <div className="text-[13px] font-semibold text-[var(--color-bone)] leading-snug line-clamp-2">
                                {title}
                              </div>
                              <span
                                className={cn(
                                  'shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded-md',
                                  isRunning && 'bg-[rgba(0,113,227,0.10)] text-[var(--color-rust)]',
                                  isPaused && 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
                                  isSuccess && 'bg-[rgba(16,185,129,0.10)] text-[var(--color-patina)]',
                                  (isFailed || isPartial) && 'bg-[rgba(239,68,68,0.10)] text-[var(--color-iron)]',
                                  !isRunning &&
                                    !isPaused &&
                                    !isSuccess &&
                                    !isFailed &&
                                    !isPartial &&
                                    'bg-black/5 dark:bg-white/5 text-[var(--color-smoke)]',
                                )}
                              >
                                {STATE_LABEL[state] || task.status}
                                {isRunning ? ` ${pct}%` : ''}
                              </span>
                            </div>

                            <div className="text-[12px] text-[var(--color-ash)] mt-1 leading-relaxed line-clamp-2">
                              {getTaskMessage(task) ||
                                (isRunning
                                  ? '正在运行…'
                                  : isPaused
                                    ? '已暂停 · 继续将从头执行'
                                    : isSuccess
                                      ? '已完成'
                                      : isFailed
                                        ? '执行失败'
                                        : '排队中')}
                            </div>

                            {err && (isFailed || isPartial || isPaused) && (
                              <div className="mt-2 text-[11px] text-[var(--color-iron)] leading-relaxed bg-[rgba(239,68,68,0.06)] rounded-lg px-2.5 py-2">
                                {err}
                              </div>
                            )}

                            {isPaused && (
                              <div className="mt-2 flex items-start gap-1.5 text-[11px] text-amber-700 dark:text-amber-400/90 leading-relaxed">
                                <Info className="size-3.5 shrink-0 mt-0.5" strokeWidth={2} />
                                <span>暂停没有断点：点「继续」会重新跑整条流水线，已完成的部分可能被跳过或重做。</span>
                              </div>
                            )}

                            {/* Progress */}
                            {isRunning && (
                              <div className="mt-3 h-1.5 rounded-full bg-black/[0.06] dark:bg-white/[0.08] overflow-hidden">
                                <div
                                  className="h-full rounded-full bg-[var(--color-rust)] ui-progress-bar"
                                  style={{ width: `${pct}%` }}
                                />
                              </div>
                            )}

                            {/* File rows */}
                            {showFileRows && (
                              <div className="mt-3 space-y-1 max-h-36 overflow-y-auto border-l-2 border-[var(--color-hairline-strong)] pl-3">
                                {fileRows.map((sub, idx) => {
                                  const ok = sub?.status === 'completed';
                                  const bad = sub?.status === 'failed';
                                  const skipped = sub?.status === 'skipped';
                                  const running = sub?.status === 'running';
                                  const fileName =
                                    sub?.title ||
                                    (sub && 'video_path' in sub && sub.video_path
                                      ? String(sub.video_path).split('/').pop()
                                      : null) ||
                                    '?';
                                  const stageText =
                                    'stage' in (sub || {}) ? (sub as { stage?: string }).stage : undefined;
                                  const errText =
                                    'error' in (sub || {}) ? (sub as { error?: string }).error : undefined;
                                  let detail = '';
                                  let detailTitle = '';
                                  if (running && stageText) {
                                    detail = stageText;
                                    detailTitle = stageText;
                                  } else if (bad) {
                                    if (errText) {
                                      const label = classifySubtaskError(
                                        sub as { error_type?: string; error?: string },
                                      );
                                      detail = label ? `[${label}]` : errText.slice(0, 40);
                                      detailTitle = `${label ? label + ' — ' : ''}${errText}`;
                                    } else if (stageText) {
                                      detail = stageText;
                                      detailTitle = stageText;
                                    }
                                  }
                                  return (
                                    <div key={idx} className="flex items-start gap-1.5 text-[11px] leading-snug">
                                      {ok ? (
                                        <CheckCircle2 className="size-3 shrink-0 mt-0.5 text-[var(--color-patina)]" />
                                      ) : bad ? (
                                        <AlertTriangle className="size-3 shrink-0 mt-0.5 text-[var(--color-iron)]" />
                                      ) : running ? (
                                        <Loader2 className="size-3 shrink-0 mt-0.5 animate-spin text-[var(--color-rust)]" />
                                      ) : skipped ? (
                                        <div className="size-2 shrink-0 mt-1 rounded-full bg-black/15 dark:bg-white/15" />
                                      ) : (
                                        <div className="size-2 shrink-0 mt-1 rounded-full bg-black/25 dark:bg-white/25" />
                                      )}
                                      <span className="truncate text-[var(--color-smoke)] flex-1" title={fileName}>
                                        {fileName}
                                      </span>
                                      {detail && (
                                        <span
                                          className={cn(
                                            'shrink-0 text-[10px] truncate max-w-[140px]',
                                            bad ? 'text-[var(--color-iron)]' : 'text-[var(--color-ash)]',
                                          )}
                                          title={detailTitle}
                                        >
                                          {detail}
                                        </span>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            )}

                            {/* Actions — large, labeled */}
                            <div className="mt-3 flex flex-wrap items-center gap-2">
                              {isRunning && (
                                <>
                                  <ActionBtn
                                    variant="warn"
                                    disabled={busy}
                                    title="暂停后恢复将从头执行"
                                    onClick={() =>
                                      void withBusy(task.task_id, async () => {
                                        if (
                                          confirm('确定暂停？\n\n注意：当前不支持断点续传。继续时会从头执行整条任务。')
                                        ) {
                                          await handlePause(task);
                                        }
                                      })
                                    }
                                  >
                                    <Pause className="size-3.5" strokeWidth={2.5} />
                                    暂停
                                  </ActionBtn>
                                  <ActionBtn
                                    variant="danger"
                                    disabled={busy}
                                    title="停止任务"
                                    onClick={() =>
                                      void withBusy(task.task_id, async () => {
                                        if (confirm(`确定停止任务？\n${title}`)) {
                                          await handleCancel(task);
                                        }
                                      })
                                    }
                                  >
                                    <Square className="size-3.5" strokeWidth={2.5} />
                                    停止
                                  </ActionBtn>
                                  <ActionBtn
                                    variant="danger"
                                    disabled={busy}
                                    title="停止并删除记录"
                                    onClick={() =>
                                      void withBusy(task.task_id, async () => {
                                        if (confirm(`确定删除此任务？\n${title}`)) {
                                          await handleDelete(task);
                                        }
                                      })
                                    }
                                  >
                                    <Trash2 className="size-3.5" />
                                    删除
                                  </ActionBtn>
                                </>
                              )}

                              {isPaused && (
                                <>
                                  <ActionBtn
                                    variant="primary"
                                    disabled={busy}
                                    title="从头重新执行"
                                    onClick={() => void withBusy(task.task_id, () => handleResume(task))}
                                  >
                                    <Play className="size-3.5" fill="currentColor" />
                                    继续（从头）
                                  </ActionBtn>
                                  <ActionBtn
                                    variant="danger"
                                    disabled={busy}
                                    onClick={() =>
                                      void withBusy(task.task_id, async () => {
                                        if (confirm(`确定删除此任务？\n${title}`)) {
                                          await handleDelete(task);
                                        }
                                      })
                                    }
                                  >
                                    <Trash2 className="size-3.5" />
                                    删除
                                  </ActionBtn>
                                </>
                              )}

                              {(isFailed || isPartial) && (
                                <ActionBtn
                                  variant="primary"
                                  disabled={busy}
                                  title={isPartial ? '只重试失败的部分' : '重新提交任务'}
                                  onClick={() => void withBusy(task.task_id, () => handleRetry(task))}
                                >
                                  <RotateCw className="size-3.5" />
                                  {isPartial ? '重试失败项' : '重试'}
                                </ActionBtn>
                              )}

                              {!isRunning && !isPaused && (
                                <ActionBtn
                                  variant="danger"
                                  disabled={busy}
                                  onClick={() =>
                                    void withBusy(task.task_id, async () => {
                                      if (confirm(`确定删除此任务记录？\n${title}`)) {
                                        await handleDelete(task);
                                      }
                                    })
                                  }
                                >
                                  <Trash2 className="size-3.5" />
                                  删除
                                </ActionBtn>
                              )}
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    );
                  })
                )}
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
