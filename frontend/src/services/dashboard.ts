import { apiClient } from '@/lib/api';

export interface HealthCheck {
  name: string;
  description: string;
  anomaly_count: number;
  samples: Array<Record<string, unknown>>;
}

export interface DashboardData {
  health: {
    status: string;
    checked_at: string;
    total_anomaly_count: number;
    checks: HealthCheck[];
  };
  tasks: {
    total: number;
    active: number;
    PENDING: number;
    RUNNING: number;
    PAUSED: number;
    COMPLETED: number;
    FAILED: number;
    PARTIAL_FAILED: number;
    CANCELLED: number;
  };
  transcribe_stages: Record<string, number>;
  account_pool: {
    total_accounts?: number;
    available_accounts?: number;
    active_uploads?: number;
    excluded?: string[];
  };
  failure_summary: {
    window_days: number;
    total_failed: number;
    buckets: Array<{
      error_type: string;
      error_stage: string;
      count: number;
      last_seen: string | null;
      sample_error: string;
    }>;
  };
  quota_status: {
    status: string;
    accounts: Array<{
      account_id: string;
      /** @deprecated 后端 dual emit，下版本会移除；新代码读 account_id */
      accountId?: string;
      account_label?: string;
      /** @deprecated 同 accountId */
      accountLabel?: string;
      remaining_hours: number;
      status: string;
    }>;
  };
  creator_sync: {
    total_creators: number;
    auto_sync_enabled: number;
    stale_sync_count: number;
  };
  uptime_seconds: number;
}

export const getDashboard = async (signal?: AbortSignal): Promise<DashboardData> => {
  const response = await apiClient.get('/metrics/dashboard', { signal });
  return response.data;
};
