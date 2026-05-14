import type { Task } from '@/lib/api';
import { taskTimestamp } from './formatters';

export type TaskFilterCategory = 'all' | 'download' | 'transcribe' | 'sync';

export function getTaskFilterCategory(taskType: string): TaskFilterCategory {
  if (taskType === 'download' || taskType.startsWith('creator_sync')) return 'download';
  if (taskType === 'pipeline' || taskType === 'local_transcribe' || taskType === 'creator_transcribe') return 'transcribe';
  if (taskType.startsWith('full_sync') || taskType === 'scan_all_following') return 'sync';
  return 'all';
}

export function filterTasksByCategory(tasks: Task[], category: TaskFilterCategory): Task[] {
  if (category === 'all') return tasks;
  return tasks.filter((t) => getTaskFilterCategory(t.task_type) === category);
}

export function sortTasks(tasks: Task[]) {
  return [...tasks].sort((a, b) => {
    const at = taskTimestamp(a) || 0;
    const bt = taskTimestamp(b) || 0;
    return bt - at;
  });
}
