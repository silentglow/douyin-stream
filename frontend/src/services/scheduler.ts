import { apiClient } from '@/lib/api';
import type { ScheduleTask } from '@/types';

export const getSchedules = async (signal?: AbortSignal): Promise<ScheduleTask[]> => {
  const response = await apiClient.get('/scheduler', { signal });
  return response.data;
};

export const addSchedule = async (cronExpr: string, enabled: boolean = true, signal?: AbortSignal): Promise<{task_id: string}> => {
  const response = await apiClient.post('/scheduler', { cron_expr: cronExpr, enabled }, { signal });
  return response.data;
};

export const toggleSchedule = async (taskId: string, enabled: boolean, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.put(`/scheduler/${taskId}/toggle`, { enabled }, { signal });
  return response.data;
};

export const deleteSchedule = async (taskId: string, signal?: AbortSignal): Promise<unknown> => {
  const response = await apiClient.delete(`/scheduler/${taskId}`, { signal });
  return response.data;
};

export const runScheduleNow = async (taskId: string, signal?: AbortSignal): Promise<{task_id: string}> => {
  const response = await apiClient.post(`/scheduler/run_now`, { task_id: taskId }, { signal });
  return response.data;
};
