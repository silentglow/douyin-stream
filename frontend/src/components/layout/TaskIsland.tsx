import { useState, useMemo, useEffect, useRef } from 'react';
import { useStore } from '@/store/useStore';
import { useTaskActions } from '@/hooks/useTaskActions';
import { getTaskDisplayState, sortTasks, filterTasksByCategory, getTaskMessage, type TaskFilterCategory } from '@/lib/task-utils';
import type { Task } from '@/lib/api';
import { Loader2, CheckCircle2, AlertTriangle, RotateCw, Trash2, ArrowUpDown, X, ListTodo } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';

// Helper to parse payload
function parsePayload(payload?: string): Record<string, unknown> | null {
  if (!payload) return null;
  try {
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

// Helper to resolve a friendly task title
function getTaskTitle(task: Task): string {
  const p = parsePayload(task.payload);
  if (p && typeof p.msg === 'string') return p.msg;
  if (p && typeof p.creator_name === 'string') return `同步: ${p.creator_name}`;
  if (p && typeof p.uid === 'string') return `同步创作者: ${p.uid.slice(0, 8)}`;
  
  switch (task.task_type) {
    case 'creator_sync_full':
    case 'creator_sync_incremental':
      return '同步创作者内容';
    case 'pipeline':
      return '音视频下载 + 转写工作流';
    case 'local_transcribe':
      return '本地媒体文件转写';
    case 'download':
      return '音视频批量下载';
    case 'transcribe':
      return '音频语音转写';
    default:
      return task.task_type || '未命名任务';
  }
}

// TABS DEFINITION
const FILTER_TABS: { key: TaskFilterCategory; label: string }[] = [
  { key: 'all',         label: '全部' },
  { key: 'download',    label: '下载' },
  { key: 'transcribe',  label: '转写' },
  { key: 'sync',        label: '同步' },
];

interface TaskIslandProps {
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
}

export function TaskIsland({ isOpen, onToggle, onClose }: TaskIslandProps) {
  const [filter, setFilter] = useState<TaskFilterCategory>('all');
  const [sortBy, setSortBy] = useState<'time' | 'priority'>('time');
  const popoverRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const rawTasks = useStore((state) => state.tasks);
  const fetchInitialTasks = useStore((state) => state.fetchInitialTasks);
  const { handleClearHistory, handleRetry } = useTaskActions();

  // Load initial tasks on mount
  useEffect(() => {
    fetchInitialTasks();
  }, [fetchInitialTasks]);

  // Close HUD on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        isOpen &&
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen, onClose]);

  // Compute status metrics
  const activeTasks = useMemo(() => {
    return rawTasks.filter((t) => {
      const s = getTaskDisplayState(t);
      return s === 'running' || s === 'paused';
    });
  }, [rawTasks]);

  const failedCount = useMemo(() => {
    return rawTasks.filter((t) => {
      const s = getTaskDisplayState(t);
      return s === 'failed' || s === 'stale';
    }).length;
  }, [rawTasks]);

  const overallProgress = useMemo(() => {
    if (activeTasks.length === 0) return 0;
    const total = activeTasks.reduce((acc, t) => acc + (t.progress || 0), 0);
    return Math.round((total / activeTasks.length) * 100);
  }, [activeTasks]);

  const sortedTasks = useMemo(() => {
    const tasks = [...rawTasks];
    if (sortBy === 'priority') {
      return tasks.sort((a, b) => (b.priority || 0) - (a.priority || 0));
    }
    return sortTasks(tasks);
  }, [rawTasks, sortBy]);

  const filteredTasks = useMemo(() => {
    return filterTasksByCategory(sortedTasks, filter);
  }, [sortedTasks, filter]);

  const hasNonRunning = useMemo(() => {
    return sortedTasks.some((t) => {
      const s = getTaskDisplayState(t);
      return s !== 'running' && s !== 'paused';
    });
  }, [sortedTasks]);

  // SVG circle math
  const radius = 9;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (overallProgress / 100) * circumference;

  return (
    <>
      {/* 1. FLOATING BUBBLE (Dynamic Island) */}
      <button
        ref={buttonRef}
        onClick={onToggle}
        className={cn(
          'fixed bottom-6 right-6 z-40 flex items-center justify-center transition-all duration-300 shadow-[0_12px_40px_rgba(0,0,0,0.5)] border cursor-pointer select-none outline-none',
          activeTasks.length > 0
            ? 'h-10 px-4 rounded-full bg-[var(--color-paper)] border-white/[0.08] hover:border-[var(--color-rust)]/35 text-[var(--color-bone)] gap-2.5'
            : failedCount > 0
              ? 'h-10 w-10 rounded-full bg-[rgba(239,68,68,0.1)] border-red-500/25 hover:border-red-500/40 text-red-400'
              : 'h-10 w-10 rounded-full bg-[var(--color-paper)]/40 hover:bg-[var(--color-paper)]/70 backdrop-blur-md border-white/[0.04] hover:border-white/[0.08] text-[var(--color-smoke)] hover:text-[var(--color-bone)]'
        )}
        title={activeTasks.length > 0 ? `${activeTasks.length} 项任务运行中...` : '任务中心 (⌘5)'}
      >
        {activeTasks.length > 0 ? (
          <>
            {/* Circular Progress Ring */}
            <div className="relative flex size-5 items-center justify-center shrink-0">
              <svg className="absolute inset-0 size-full -rotate-90" viewBox="0 0 24 24">
                <circle
                  cx="12"
                  cy="12"
                  r={radius}
                  fill="none"
                  stroke="rgba(255, 255, 255, 0.05)"
                  strokeWidth="2"
                />
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
                  className="transition-all duration-300"
                />
              </svg>
              <span className="font-mono text-[9px] font-bold text-[var(--color-rust)] mt-[0.5px]">
                {activeTasks.length}
              </span>
            </div>
            
            {/* Label */}
            <span className="text-[12px] font-semibold tracking-wide">
              {overallProgress}%
            </span>
            <span className="relative flex size-1.5 shrink-0 rounded-full bg-[var(--color-rust)]">
              <span className="absolute inset-0 rounded-full bg-[var(--color-rust)] animate-ping opacity-75" />
            </span>
          </>
        ) : failedCount > 0 ? (
          <div className="relative">
            <AlertTriangle className="size-4" strokeWidth={2.2} />
            <span className="absolute -top-1 -right-1 size-2 rounded-full bg-red-500" />
          </div>
        ) : (
          <ListTodo className="size-4" strokeWidth={1.8} />
        )}
      </button>

      {/* 2. HUD POPOVER PANEL */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            ref={popoverRef}
            initial={{ opacity: 0, y: 15, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 15, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 380, damping: 30 }}
            className="fixed bottom-20 right-6 z-40 w-[380px] max-w-[calc(100vw-3rem)] bg-[var(--color-paper)]/95 backdrop-blur-2xl border border-white/[0.06] rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.6)] flex flex-col overflow-hidden max-h-[460px]"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-hairline)] flex-shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-[13.5px] font-semibold text-[var(--color-bone)]">任务队列</span>
                {activeTasks.length > 0 && (
                  <span className="px-1.5 py-0.5 rounded-md bg-[var(--color-rust)]/10 text-[9.5px] text-[var(--color-rust)] font-bold">
                    {activeTasks.length} 运行中
                  </span>
                )}
              </div>
              
              <button
                onClick={onClose}
                className="p-1 rounded-md hover:bg-white/5 text-[var(--color-smoke)] hover:text-[var(--color-bone)] transition-colors cursor-pointer"
              >
                <X className="size-4" />
              </button>
            </div>

            {/* Filter controls */}
            <div className="px-5 py-2.5 flex items-center justify-between gap-4 border-b border-[var(--color-hairline)] bg-white/[0.005] flex-shrink-0">
              <div className="flex items-center gap-1.5">
                {FILTER_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setFilter(tab.key)}
                    className={cn(
                      'px-2.5 py-1 text-[11px] font-bold rounded-lg transition-all cursor-pointer',
                      filter === tab.key
                        ? 'bg-white/5 text-[var(--color-rust)]'
                        : 'text-[var(--color-smoke)] hover:text-[var(--color-bone)]'
                    )}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1">
                <button
                  onClick={() => setSortBy(s => s === 'time' ? 'priority' : 'time')}
                  title="切换排序"
                  className="p-1 rounded-md border border-white/5 bg-white/5 text-[var(--color-smoke)] hover:text-[var(--color-bone)] hover:bg-white/10 transition-all cursor-pointer"
                >
                  <ArrowUpDown className="size-3.5" />
                </button>
                {hasNonRunning && (
                  <button
                    onClick={handleClearHistory}
                    title="清除历史任务"
                    className="p-1 rounded-md text-[var(--color-iron)] hover:bg-[var(--color-iron)]/10 transition-colors cursor-pointer"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* Task list */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 select-none">
              {filteredTasks.length === 0 ? (
                <div className="py-20 text-center">
                  <div className="text-[14px] font-medium text-[var(--color-smoke)]">暂无队列任务</div>
                  <div className="text-[11px] text-[var(--color-ash)] mt-1">当前分类下没有相关任务</div>
                </div>
              ) : (
                filteredTasks.map((task) => {
                  const state = getTaskDisplayState(task);
                  const isRunning = state === 'running';
                  const isPaused = state === 'paused';
                  const isFailed = state === 'failed' || state === 'stale';
                  const isPartial = state === 'partial';
                  const isSuccess = state === 'success';
                  
                  const pct = Math.round((task.progress || 0) * 100);
                  const title = getTaskTitle(task);

                  return (
                    <div
                      key={task.task_id}
                      className={cn(
                        'relative overflow-hidden p-3 rounded-xl border flex flex-col justify-between transition-all duration-200 group',
                        isRunning
                          ? 'bg-white/[0.015] border-white/[0.04]'
                          : 'bg-transparent border-transparent hover:bg-white/[0.005]'
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        {/* Icon */}
                        <div className="mt-[2px] shrink-0">
                          {isRunning ? (
                            <Loader2 className="size-4 animate-spin text-[var(--color-rust)]" strokeWidth={2.2} />
                          ) : isPaused ? (
                            <div className="size-2 rounded-full bg-warning mt-1" />
                          ) : isFailed ? (
                            <AlertTriangle className="size-4 text-[var(--color-iron)]" strokeWidth={2.2} />
                          ) : isSuccess ? (
                            <CheckCircle2 className="size-4 text-[var(--color-patina)]" strokeWidth={2} />
                          ) : (
                            <div className="size-2 rounded-full bg-white/20 mt-1" />
                          )}
                        </div>

                        {/* Title & Stage */}
                        <div className="min-w-0 flex-1">
                          <div className="text-[12px] font-semibold text-[var(--color-bone)] truncate leading-tight">
                            {title}
                          </div>
                          <div className="text-[10px] text-[var(--color-smoke)] mt-0.5 font-medium truncate">
                            {getTaskMessage(task) || (isRunning ? '正在运行中...' : isSuccess ? '已成功完成' : isFailed ? '执行失败' : '排队中')}
                          </div>
                        </div>

                        {/* Percent or Action */}
                        <div className="shrink-0 flex items-center justify-end text-right min-w-[32px]">
                          {isRunning ? (
                            <span className="font-mono text-[11px] font-bold text-[var(--color-rust)]">
                              {pct}%
                            </span>
                          ) : isFailed || isPartial ? (
                            <button
                              onClick={() => handleRetry(task)}
                              title={isPartial ? '只重试失败子任务' : '重试任务'}
                              className="p-1 rounded-md hover:bg-white/5 text-[var(--color-smoke)] hover:text-[var(--color-bone)] cursor-pointer"
                            >
                              <RotateCw className="size-3.5" />
                            </button>
                          ) : isSuccess ? (
                            <span className="text-[10px] text-[var(--color-patina)] font-medium">完成</span>
                          ) : (
                            <span className="text-[10px] text-[var(--color-smoke)]">等待</span>
                          )}
                        </div>
                      </div>

                      {/* Thin Progress bar for running tasks */}
                      {isRunning && (
                        <div className="absolute bottom-0 left-0 right-0 h-[2.5px] bg-white/[0.03] overflow-hidden">
                          <div
                            className="h-full bg-[var(--color-rust)] transition-all duration-300"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
