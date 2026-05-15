import { useState, useMemo, useCallback, useEffect } from 'react';
import { Activity, AlertTriangle, Clock3, Loader2, Trash2, ArrowUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useStore } from '@/store/useStore';
import {
  getTaskDisplayState,
  sortTasks,
  filterTasksByCategory,
  type TaskFilterCategory,
} from '@/lib/task-utils';
import { useTaskActions } from '@/hooks/useTaskActions';
import { TaskItem } from './TaskMonitorPanel/TaskItem';

const FILTER_TABS: { key: TaskFilterCategory; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'download', label: '下载' },
  { key: 'transcribe', label: '转写' },
  { key: 'sync', label: '同步' },
];

export default function Tasks() {
  const [filter, setFilter] = useState<TaskFilterCategory>('all');
  const [sortBy, setSortBy] = useState<'time' | 'priority'>('time');
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const rawTasks = useStore((state) => state.tasks);
  const fetchInitialTasks = useStore((state) => state.fetchInitialTasks);

  const { handleClearHistory, handleRetry } = useTaskActions();

  useEffect(() => {
    fetchInitialTasks();
  }, [fetchInitialTasks]);

  const sortedTasks = useMemo(() => {
    const tasks = [...rawTasks];
    if (sortBy === 'priority') {
      return tasks.sort((a, b) => (b.priority || 0) - (a.priority || 0));
    }
    return sortTasks(tasks);
  }, [rawTasks, sortBy]);

  const filteredTasks = useMemo(() => filterTasksByCategory(sortedTasks, filter), [sortedTasks, filter]);

  const activeTasks = useMemo(() => sortedTasks.filter((task) => {
    const state = getTaskDisplayState(task);
    return state === 'running' || state === 'paused';
  }), [sortedTasks]);

  const failedTasks = useMemo(() => sortedTasks.filter((task) => {
    const state = getTaskDisplayState(task);
    return state === 'failed' || state === 'stale';
  }), [sortedTasks]);

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
    <div className="h-full p-7 px-8 max-sm:p-4 max-sm:pb-20 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2.5">
          <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10">
            <Activity className="size-5 text-primary" />
          </div>
          <span className="text-title-1 font-bold">任务中心</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-border/60 px-2 py-1">
            <button
              onClick={() => setSortBy('time')}
              className={cn(
                'px-3 py-1 text-sm rounded-md transition-colors',
                sortBy === 'time' ? 'bg-secondary text-foreground font-medium' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              时间
            </button>
            <button
              onClick={() => setSortBy('priority')}
              className={cn(
                'flex items-center gap-1 px-3 py-1 text-sm rounded-md transition-colors',
                sortBy === 'priority' ? 'bg-secondary text-foreground font-medium' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <ArrowUpDown className="size-3.5" />
              优先级
            </button>
          </div>
          {hasNonRunning && (
            <button
              onClick={handleClearHistory}
              className="flex items-center gap-1.5 h-9 px-3 rounded-lg border border-border/60 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            >
              <Trash2 className="size-4" />
              清除历史
            </button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { label: '进行中', value: activeTasks.length, tone: 'text-primary', icon: <Loader2 className="size-4 animate-spin" /> },
          { label: '成功', value: sortedTasks.filter((t) => getTaskDisplayState(t) === 'success').length, tone: 'text-success', icon: <Activity className="size-4" /> },
          { label: '失败', value: failedTasks.length, tone: 'text-destructive', icon: <AlertTriangle className="size-4" /> },
          { label: '总计', value: sortedTasks.length, tone: 'text-foreground', icon: <Clock3 className="size-4" /> },
        ].map((item) => (
          <div key={item.label} className="rounded-[22px] border border-border/60 bg-card p-5 apple-shadow-widget">
            <div className="flex items-center justify-between">
              <div className="text-caption text-muted-foreground">{item.label}</div>
              <div className={cn('text-muted-foreground/50', item.tone)}>{item.icon}</div>
            </div>
            <div className={cn('mt-2 text-2xl font-bold', item.tone)}>{item.value}</div>
          </div>
        ))}
      </div>

      {/* Filter Tabs */}
      <div className="mb-6">
        <div className="inline-flex rounded-xl border border-border/60 bg-muted p-1">
          {FILTER_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={cn(
                'h-9 rounded-lg px-5 text-sm font-medium transition-all duration-200',
                filter === tab.key
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Task List */}
      {filteredTasks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="flex size-16 items-center justify-center rounded-2xl bg-muted">
            <Clock3 className="size-6 text-muted-foreground/40" />
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            {filter === 'all' ? '还没有后台任务' : '没有相关任务'}
          </p>
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
  );
}
