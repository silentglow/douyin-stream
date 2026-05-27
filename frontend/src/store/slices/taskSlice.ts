import type { StateCreator } from 'zustand';
import type { Task } from '@/lib/api';
import { getTaskHistory } from '@/lib/api';
import type { StoreState } from '../useStore';

const MAX_TASKS = 200;

// 终态集合（任务不再推进进度）；超容时优先淘汰这里的旧任务。
// PARTIAL_FAILED 是 RUNNING 的合法终态：批量任务里部分子任务失败、部分成功。
const TERMINAL_STATUSES = ['COMPLETED', 'FAILED', 'CANCELLED', 'PARTIAL_FAILED'] as const;

// "已结束"集合：触发 lastCompletedTaskTime 和 creator/asset 列表刷新。
// PARTIAL_FAILED 也算 —— 部分下载/转写成功的子任务已经入库，UI 该刷新。
const DONE_STATUSES = ['COMPLETED', 'PARTIAL_FAILED'] as const;

export interface TaskSlice {
  activeTaskId: string | null;
  setActiveTaskId: (id: string | null) => void;
  tasks: Task[];
  setTasks: (tasks: Task[]) => void;
  updateTask: (taskUpdate: Partial<Task> & { task_id: string }) => void;
  addTask: (task: Task) => void;
  updateTaskPriority: (taskId: string, priority: number) => void;
  fetchInitialTasks: () => Promise<void>;
  lastCompletedTaskTime: number;
  lastCompletedTaskType: string | null;
}

let fetchTasksPromise: Promise<void> | null = null;

export const createTaskSlice: StateCreator<StoreState, [], [], TaskSlice> = (set) => ({
  activeTaskId: null,
  setActiveTaskId: (id) => set({ activeTaskId: id }),
  tasks: [],
  lastCompletedTaskTime: 0,
  lastCompletedTaskType: null,
  setTasks: (tasks) => set({ tasks }),

  updateTask: (taskUpdate) => {
    set((state) => {
      let isCompleted = false;
      let completedType: string | null = null;
      const existingTaskIndex = state.tasks.findIndex((t) => t.task_id === taskUpdate.task_id);
      let updatedTasks = [...state.tasks];

      if (existingTaskIndex >= 0) {
        const oldStatus = updatedTasks[existingTaskIndex].status;
        // 过滤掉 undefined 值，防止覆盖已有数据
        const filteredUpdate = Object.fromEntries(
          Object.entries(taskUpdate).filter(([, v]) => v !== undefined),
        );
        updatedTasks[existingTaskIndex] = { ...updatedTasks[existingTaskIndex], ...filteredUpdate };
        // 将 WS 推送的 _msg / _pp / _subtasks 合并到 payload JSON 中
        const wsData = taskUpdate as Record<string, unknown>;
        if ((wsData._msg || wsData._pp || wsData._subtasks) && updatedTasks[existingTaskIndex].payload) {
          try {
            const existing = JSON.parse(updatedTasks[existingTaskIndex].payload);
            if (wsData._msg) existing.msg = wsData._msg;
            if (wsData._pp) existing.pipeline_progress = wsData._pp;
            if (wsData._subtasks) existing.subtasks = wsData._subtasks;
            updatedTasks[existingTaskIndex] = {
              ...updatedTasks[existingTaskIndex],
              payload: JSON.stringify(existing),
            };
          } catch { /* ignore parse errors */ }
        }
        // 从 filteredUpdate 中删除内部字段，避免污染 Task 对象
        if (wsData._msg !== undefined) delete (updatedTasks[existingTaskIndex] as unknown as Record<string, unknown>)._msg;
        if (wsData._pp !== undefined) delete (updatedTasks[existingTaskIndex] as unknown as Record<string, unknown>)._pp;
        if (wsData._subtasks !== undefined) delete (updatedTasks[existingTaskIndex] as unknown as Record<string, unknown>)._subtasks;
        if (
          !DONE_STATUSES.includes(oldStatus as (typeof DONE_STATUSES)[number]) &&
          DONE_STATUSES.includes(taskUpdate.status as (typeof DONE_STATUSES)[number])
        ) {
          isCompleted = true;
          completedType = updatedTasks[existingTaskIndex].task_type || null;
        }
      } else {
        const msg = (taskUpdate as { msg?: unknown }).msg;
        const newTask = {
          task_id: taskUpdate.task_id,
          task_type: taskUpdate.task_type || 'pipeline',
          status: taskUpdate.status || 'RUNNING',
          progress: taskUpdate.progress || 0,
          payload: taskUpdate.payload || JSON.stringify({ msg: typeof msg === 'string' ? msg : '' }),
          error_msg: taskUpdate.error_msg,
        } as Task;
        updatedTasks = [newTask, ...state.tasks];
        if (DONE_STATUSES.includes(newTask.status as (typeof DONE_STATUSES)[number])) {
          isCompleted = true;
          completedType = newTask.task_type;
        }
      }

      const creatorRelatedTypes = [
        'pipeline',
        'download',
        'batch_pipeline',
        'creator_sync_incremental',
        'creator_sync_full',
        'full_sync_incremental',
        'full_sync_full',
      ];
      const shouldResetCreators = isCompleted && completedType ? creatorRelatedTypes.includes(completedType) : false;

      // 超出上限时淘汰已完成/失败/取消的旧任务
      if (updatedTasks.length > MAX_TASKS) {
        const terminal = updatedTasks.filter((t) =>
          TERMINAL_STATUSES.includes(t.status as (typeof TERMINAL_STATUSES)[number]),
        );
        const active = updatedTasks.filter(
          (t) => !TERMINAL_STATUSES.includes(t.status as (typeof TERMINAL_STATUSES)[number]),
        );
        const toEvict = Math.max(0, updatedTasks.length - MAX_TASKS);
        if (toEvict > 0 && terminal.length > 0) {
          terminal.sort((a, b) => (b.update_time || '').localeCompare(a.update_time || ''));
          updatedTasks = [...active, ...terminal.slice(0, terminal.length - toEvict)];
        }
      }

      return {
        tasks: updatedTasks,
        ...(isCompleted
          ? {
              lastCompletedTaskTime: Date.now(),
              lastCompletedTaskType: completedType,
              ...(shouldResetCreators ? { creatorsLoadedAt: 0, assetsLoadedAt: 0 } : { assetsLoadedAt: 0 }),
            }
          : {}),
      };
    });
  },

  addTask: (task) => {
    set((state) => {
      const existingIndex = state.tasks.findIndex((t) => t.task_id === task.task_id);
      let updatedTasks = [...state.tasks];

      if (existingIndex >= 0) {
        updatedTasks[existingIndex] = task;
      } else {
        updatedTasks = [task, ...updatedTasks];
      }

      if (updatedTasks.length > MAX_TASKS) {
        const terminal = updatedTasks.filter((t) =>
          TERMINAL_STATUSES.includes(t.status as (typeof TERMINAL_STATUSES)[number]),
        );
        const active = updatedTasks.filter(
          (t) => !TERMINAL_STATUSES.includes(t.status as (typeof TERMINAL_STATUSES)[number]),
        );
        const toEvict = Math.max(0, updatedTasks.length - MAX_TASKS);
        if (toEvict > 0 && terminal.length > 0) {
          terminal.sort((a, b) => (b.update_time || '').localeCompare(a.update_time || ''));
          updatedTasks = [...active, ...terminal.slice(0, terminal.length - toEvict)];
        }
      }

      return { tasks: updatedTasks };
    });
  },

  updateTaskPriority: (taskId, priority) => {
    set((state) => ({
      tasks: state.tasks.map((t) =>
        t.task_id === taskId ? { ...t, priority } : t
      ),
    }));
  },

  fetchInitialTasks: async () => {
    if (fetchTasksPromise) return fetchTasksPromise;

    fetchTasksPromise = (async () => {
      try {
        const history = await getTaskHistory();
        set((state) => {
          const historyMap = new Map(history.map((t) => [t.task_id, t]));
          // 保留 store 中 WS 已有但 REST 未返回的任务（正在运行中尚未持久化）
          const wsOnlyTasks = state.tasks.filter((t) => !historyMap.has(t.task_id));
          // REST 返回的任务：优先用 WS 的实时进度
          const merged = history.map((t) => {
            const wsTask = state.tasks.find((s) => s.task_id === t.task_id);
            if (wsTask && wsTask.update_time && t.update_time) {
              return new Date(wsTask.update_time) > new Date(t.update_time) ? wsTask : t;
            }
            return wsTask && wsTask.progress > t.progress ? wsTask : t;
          });
          return { tasks: [...merged, ...wsOnlyTasks] };
        });
      } catch (error) {
        console.error('Failed to fetch initial task history', error);
      } finally {
        fetchTasksPromise = null;
      }
    })();

    return fetchTasksPromise;
  },
});
