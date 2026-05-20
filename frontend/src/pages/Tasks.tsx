import { useState, useMemo, useCallback, useEffect } from 'react';
import { Trash2, ArrowUpDown } from 'lucide-react';
import NumberFlow from '@number-flow/react';
import { cn } from '@/lib/utils';
import { useStore } from '@/store/useStore';
import {
  getTaskDisplayState,
  sortTasks,
  filterTasksByCategory,
  type TaskFilterCategory,
} from '@/lib/task-utils';
import { useTaskActions } from '@/hooks/useTaskActions';
import { TaskItem } from '@/components/layout/TaskMonitorPanel/TaskItem';

const FILTER_TABS: { key: TaskFilterCategory; label: string }[] = [
  { key: 'all',         label: '全部'    },
  { key: 'download',    label: '下载'    },
  { key: 'transcribe',  label: '转写'    },
  { key: 'sync',        label: '同步'    },
];

export default function Tasks() {
  const [filter, setFilter] = useState<TaskFilterCategory>('all');
  const [sortBy, setSortBy] = useState<'time' | 'priority'>('time');
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const rawTasks = useStore((state) => state.tasks);
  const fetchInitialTasks = useStore((state) => state.fetchInitialTasks);

  const { handleClearHistory, handleRetry } = useTaskActions();

  useEffect(() => { fetchInitialTasks(); }, [fetchInitialTasks]);

  const sortedTasks = useMemo(() => {
    const tasks = [...rawTasks];
    if (sortBy === 'priority') {
      return tasks.sort((a, b) => (b.priority || 0) - (a.priority || 0));
    }
    return sortTasks(tasks);
  }, [rawTasks, sortBy]);

  const filteredTasks = useMemo(() => filterTasksByCategory(sortedTasks, filter), [sortedTasks, filter]);

  const activeCount = useMemo(() => sortedTasks.filter((t) => {
    const s = getTaskDisplayState(t);
    return s === 'running' || s === 'paused';
  }).length, [sortedTasks]);

  const successCount = useMemo(() => sortedTasks.filter((t) => getTaskDisplayState(t) === 'success').length, [sortedTasks]);
  const failedCount = useMemo(() => sortedTasks.filter((t) => {
    const s = getTaskDisplayState(t);
    return s === 'failed' || s === 'stale';
  }).length, [sortedTasks]);

  const hasNonRunning = useMemo(() => sortedTasks.some((t) => {
    const state = getTaskDisplayState(t);
    return state !== 'running' && state !== 'paused';
  }), [sortedTasks]);

  const toggleExpand = useCallback((taskId: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  }, []);

  return (
    <div className="h-full overflow-y-auto page-enter">
      {/* ═══ MASTHEAD ═══════════════════════════════════════════ */}
      <header className="px-10 pt-12 pb-9 border-b border-[var(--color-hairline)]">
        <div className="flex items-end justify-between gap-10">
          <div>
            <div className="flex items-center gap-2 mb-4">
              {activeCount > 0 ? (
                <>
                  <span className="status-dot bg-[var(--color-rust)] pulse-dot" />
                  <span className="text-[11px] tracking-[0.16em] uppercase text-[var(--color-rust)]">{activeCount} 项运行中</span>
                </>
              ) : (
                <>
                  <span className="status-dot bg-[var(--color-patina)]" />
                  <span className="eyebrow text-[var(--color-patina)]">队列空闲</span>
                </>
              )}
            </div>
            <h1 className="font-display text-[clamp(48px,6.5vw,96px)] leading-[0.95] tracking-display text-[var(--color-bone)]">
              任务中心
            </h1>
          </div>

          <div className="flex items-end gap-2 pb-2">
            <div className="flex items-center border border-[var(--color-hairline-strong)]">
              <button
                onClick={() => setSortBy('time')}
                className={cn(
                  'px-3 py-2 text-[12px] font-medium transition-colors',
                  sortBy === 'time'
                    ? 'bg-[var(--color-vellum)] text-[var(--color-bone)]'
                    : 'text-[var(--color-smoke)] hover:text-[var(--color-bone)]'
                )}
              >
                时间
              </button>
              <button
                onClick={() => setSortBy('priority')}
                className={cn(
                  'px-3 py-2 text-[12px] font-medium transition-colors flex items-center gap-1',
                  sortBy === 'priority'
                    ? 'bg-[var(--color-vellum)] text-[var(--color-bone)]'
                    : 'text-[var(--color-smoke)] hover:text-[var(--color-bone)]'
                )}
              >
                <ArrowUpDown className="w-3 h-3" />
                优先级
              </button>
            </div>
            {hasNonRunning && (
              <button
                onClick={handleClearHistory}
                className="btn-sharp flex items-center gap-2"
              >
                <Trash2 className="w-3 h-3" />
                清除历史
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ═══ STATS — 4 columns ══════════════════════════════════ */}
      <section className="px-10 py-10 border-b border-[var(--color-hairline)]">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 stagger">
          {[
            { label: '运行中', value: activeCount,           accent: activeCount > 0 },
            { label: '成功',   value: successCount,          tone: 'patina' as const },
            { label: '失败',   value: failedCount,           tone: failedCount > 0 ? 'iron' as const : undefined },
            { label: '总计',   value: sortedTasks.length     },
          ].map((s) => (
            <div key={s.label} className="bg-[var(--color-paper)] border border-white/[0.03] hover:border-[var(--color-rust)]/25 hover:bg-[rgba(99,102,241,0.02)] hover:shadow-[0_8px_30px_rgba(0,0,0,0.2)] rounded-[var(--radius-card)] p-6 transition-all duration-300 flex flex-col justify-between min-h-[148px]">
              <div>
                <div className="text-[10px] font-bold tracking-widest text-[var(--color-smoke)] uppercase mb-2">{s.label}</div>
                <div className={cn(
                  'numeral text-[clamp(48px,6.5vw,88px)]',
                  s.tone === 'patina' && 'text-[var(--color-patina)]',
                  s.tone === 'iron' && 'text-[var(--color-iron)]',
                  s.accent && 'text-[var(--color-rust)]'
                )}>
                  <NumberFlow
                    value={s.value}
                    transformTiming={{ duration: 700, easing: 'cubic-bezier(0.2, 0.9, 0.3, 1)' }}
                    spinTiming={{ duration: 700, easing: 'cubic-bezier(0.2, 0.9, 0.3, 1)' }}
                  />
                </div>
              </div>
              <div className="mt-3 text-[11.5px] text-[var(--color-ash)] font-medium leading-none">
                {s.label === '运行中' ? '排队或运行中任务' : s.label === '成功' ? '正常完成的任务' : s.label === '失败' ? '遇到异常的任务' : '全部历史任务数'}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ═══ FILTER TABS ════════════════════════════════════════ */}
      <section className="px-10 pt-6 pb-4 flex items-center gap-4 border-b border-[var(--color-hairline)]">
        <span className="eyebrow">筛选</span>
        <div className="flex items-center gap-1">
          {FILTER_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={cn(
                'px-3 py-1.5 text-[12px] font-medium transition-colors border-b',
                filter === tab.key
                  ? 'text-[var(--color-rust)] border-[var(--color-rust)]'
                  : 'text-[var(--color-smoke)] hover:text-[var(--color-bone)] border-transparent'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {/* ═══ LIST ═══════════════════════════════════════════════ */}
      <div className="px-10 py-8">
        {filteredTasks.length === 0 ? (
          <div className="py-24 text-center">
            <div className="font-display text-[32px] text-[var(--color-smoke)] leading-tight mb-2">
              队列暂时安静
            </div>
            <div className="text-[13px] text-[var(--color-ash)]">
              {filter === 'all' ? '还没有后台任务' : '此类型暂无任务'}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredTasks.map((task) => (
              <TaskItem
                key={task.task_id}
                task={task}
                onRetry={handleRetry}
                isExpanded={expandedTasks.has(task.task_id)}
                onToggleExpand={toggleExpand}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
