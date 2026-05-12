import { useCallback, useEffect, useState, useMemo } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Cpu,
  HardDrive,
  Loader2,
  RefreshCw,
  Server,
  Users,
  XCircle,
  Zap,
} from 'lucide-react';
import { getDashboard, type DashboardData, type HealthCheck } from '@/lib/api';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { PageShell } from '@/components/layout/PageShell';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

const TASK_STATUS_CONFIG: Record<string, { label: string; colorClass: string; icon: typeof Activity }> = {
  PENDING: { label: '等待中', colorClass: 'text-muted-foreground', icon: Clock },
  RUNNING: { label: '运行中', colorClass: 'text-primary', icon: RefreshCw },
  PAUSED: { label: '已暂停', colorClass: 'text-warning', icon: Clock },
  COMPLETED: { label: '已完成', colorClass: 'text-success', icon: CheckCircle2 },
  FAILED: { label: '失败', colorClass: 'text-destructive', icon: XCircle },
  PARTIAL_FAILED: { label: '部分失败', colorClass: 'text-warning', icon: AlertTriangle },
  CANCELLED: { label: '已取消', colorClass: 'text-muted-foreground', icon: XCircle },
};

const ERROR_TYPE_LABELS: Record<string, string> = {
  quota: '额度不足',
  network: '网络异常',
  timeout: '请求超时',
  auth: '鉴权失败',
  file: '文件错误',
  validation: '参数错误',
  unknown: '未知错误',
};

const STAGE_LABELS: Record<string, string> = {
  uploading: '上传中',
  uploaded: '上传完成',
  transcribing: '转写中',
  exporting: '导出中',
  downloading: '下载结果',
  saved: '落盘',
  failed: '失败',
  queued: '排队中',
  unknown: '未知',
};

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatRelativeTime(iso: string | null) {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return '—';
  const diff = Date.now() - t;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < minute) return '刚刚';
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`;
  return `${Math.floor(diff / day)} 天前`;
}

function HealthCheckCard({ check }: { check: HealthCheck }) {
  const hasAnomaly = check.anomaly_count > 0;
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-[10px] border px-3 py-2.5',
        hasAnomaly
          ? 'border-destructive/30 bg-destructive/5'
          : 'border-border/60 bg-secondary/30'
      )}
    >
      {hasAnomaly ? (
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
      ) : (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-foreground">{check.description}</span>
          {hasAnomaly && (
            <span className="rounded-full bg-destructive/10 px-1.5 py-0.5 text-[11px] font-semibold text-destructive">
              {check.anomaly_count}
            </span>
          )}
        </div>
        {hasAnomaly && check.samples.length > 0 && (
          <div className="mt-1.5 space-y-1">
            {check.samples.map((s, i) => (
              <pre
                key={i}
                className="overflow-x-auto rounded-md bg-background/80 px-2 py-1 text-[11px] text-muted-foreground"
              >
                {JSON.stringify(s, null, 2)}
              </pre>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  colorClass,
}: {
  label: string;
  value: number | string;
  sub?: string;
  icon: typeof Activity;
  colorClass: string;
}) {
  return (
    <Card size="sm" hoverable={false} className="flex items-center gap-3">
      <div className={cn('flex size-9 items-center justify-center rounded-[10px] bg-secondary', colorClass)}>
        <Icon className="size-4" />
      </div>
      <div>
        <div className="text-lg font-bold leading-tight text-foreground">{value}</div>
        <div className="text-[11px] text-muted-foreground">{label}</div>
        {sub && <div className="text-[11px] text-muted-foreground/70">{sub}</div>}
      </div>
    </Card>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getDashboard();
      setData(d);
    } catch {
      setError('加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 30000);
    return () => clearInterval(timer);
  }, [fetchData]);

  const health = data?.health;
  const tasks = data?.tasks;
  const stages = data?.transcribe_stages;
  const pool = data?.account_pool;
  const failures = data?.failure_summary;
  const quota = data?.quota_status;
  const creators = data?.creator_sync;

  const totalTranscribeRuns = useMemo(() => {
    if (!stages) return 0;
    return Object.values(stages).reduce((a, b) => a + (typeof b === 'number' ? b : 0), 0);
  }, [stages]);

  const stageEntries = useMemo(() => {
    if (!stages) return [];
    const order = ['queued', 'uploaded', 'transcribing', 'exporting', 'downloading', 'saved', 'failed'];
    const entries = Object.entries(stages).sort((a, b) => {
      const ia = order.indexOf(a[0]);
      const ib = order.indexOf(b[0]);
      if (ia !== -1 && ib !== -1) return ia - ib;
      if (ia !== -1) return -1;
      if (ib !== -1) return 1;
      return a[0].localeCompare(b[0]);
    });
    return entries;
  }, [stages]);

  return (
    <PageShell>
      <PageHeader
        title="系统仪表盘"
        description="一目了然看清整个系统的健康状态"
        actions={
          <Button
            variant="ghost"
            size="sm"
            onClick={() => fetchData()}
            disabled={loading}
            className="gap-1.5"
          >
            <RefreshCw className={cn('size-4', loading && 'animate-spin')} />
            刷新
          </Button>
        }
      />

      {error && (
        <div className="mb-4 rounded-[10px] border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Top stats row */}
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="活跃任务"
          value={tasks?.active ?? 0}
          sub={`运行中 ${tasks?.RUNNING ?? 0}`}
          icon={Activity}
          colorClass="text-primary"
        />
        <StatCard
          label="转写流水线"
          value={totalTranscribeRuns}
          sub={`进行中 ${(stages?.transcribing ?? 0) + (stages?.uploading ?? 0) + (stages?.exporting ?? 0)}`}
          icon={Server}
          colorClass="text-success"
        />
        <StatCard
          label="Qwen 账号"
          value={pool?.total_accounts ?? 0}
          sub={`可用 ${pool?.available_accounts ?? 0}`}
          icon={Zap}
          colorClass="text-warning"
        />
        <StatCard
          label="运行时长"
          value={formatUptime(data?.uptime_seconds ?? 0)}
          icon={HardDrive}
          colorClass="text-muted-foreground"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Left column: Health + Tasks */}
        <div className="space-y-5 lg:col-span-2">
          {/* Health checks */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {health && health.status === 'healthy' ? (
                    <CheckCircle2 className="size-5 text-success" />
                  ) : (
                    <AlertTriangle className="size-5 text-destructive" />
                  )}
                  <CardTitle>健康检查</CardTitle>
                </div>
                <span className="text-[11px] text-muted-foreground">
                  {health ? formatRelativeTime(health.checked_at) : '—'}
                </span>
              </div>
              <CardDescription>
                {health?.total_anomaly_count
                  ? `发现 ${health.total_anomaly_count} 个异常，建议排查`
                  : '所有检查项正常'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {health ? (
                health.checks.map((c) => <HealthCheckCard key={c.name} check={c} />)
              ) : (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" /> 加载中…
                </div>
              )}
            </CardContent>
          </Card>

          {/* Task status distribution */}
          <Card>
            <CardHeader>
              <CardTitle>任务状态分布</CardTitle>
              <CardDescription>task_queue 全表统计</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {Object.entries(TASK_STATUS_CONFIG).map(([key, cfg]) => {
                  const count = ((tasks as Record<string, number> | undefined)?.[key]) ?? 0;
                  const Icon = cfg.icon;
                  return (
                    <div
                      key={key}
                      className={cn(
                        'flex items-center gap-2 rounded-[10px] border px-3 py-2',
                        count > 0 ? 'border-border/60 bg-secondary/30' : 'border-border/40 bg-secondary/10'
                      )}
                    >
                      <Icon className={cn('size-4 shrink-0', cfg.colorClass)} />
                      <div>
                        <div className="text-sm font-semibold text-foreground">{count}</div>
                        <div className="text-[11px] text-muted-foreground">{cfg.label}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Transcribe pipeline stages */}
          <Card>
            <CardHeader>
              <CardTitle>转写流水线阶段</CardTitle>
              <CardDescription>transcribe_runs 表 stage 分布</CardDescription>
            </CardHeader>
            <CardContent>
              {stageEntries.length === 0 ? (
                <div className="text-sm text-muted-foreground">暂无转写记录</div>
              ) : (
                <div className="space-y-2">
                  {stageEntries.map(([stage, count]) => {
                    const pct = totalTranscribeRuns > 0 ? Math.round((count / totalTranscribeRuns) * 100) : 0;
                    return (
                      <div key={stage} className="flex items-center gap-3">
                        <div className="w-20 shrink-0 text-xs text-muted-foreground">
                          {STAGE_LABELS[stage] ?? stage}
                        </div>
                        <div className="flex-1">
                          <div className="h-2 overflow-hidden rounded-full bg-secondary">
                            <div
                              className={cn(
                                'h-full rounded-full transition-all',
                                stage === 'saved'
                                  ? 'bg-success'
                                  : stage === 'failed'
                                    ? 'bg-destructive'
                                    : 'bg-primary'
                              )}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                        <div className="w-12 text-right text-xs font-medium text-foreground">
                          {count}
                        </div>
                        <div className="w-10 text-right text-[11px] text-muted-foreground">
                          {pct}%
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Failure summary */}
          <Card>
            <CardHeader>
              <CardTitle>最近 7 天失败原因</CardTitle>
              <CardDescription>
                共 <span className="font-semibold text-foreground">{failures?.total_failed ?? 0}</span> 次失败
              </CardDescription>
            </CardHeader>
            <CardContent>
              {failures && failures.buckets.length > 0 ? (
                <div className="overflow-hidden rounded-md border border-border/60">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50 text-muted-foreground">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium">错误类型</th>
                        <th className="px-3 py-2 text-left font-medium">阶段</th>
                        <th className="px-3 py-2 text-right font-medium">次数</th>
                        <th className="px-3 py-2 text-left font-medium">最近一次</th>
                      </tr>
                    </thead>
                    <tbody>
                      {failures.buckets.map((b, i) => (
                        <tr key={`${b.error_type}-${b.error_stage}-${i}`} className="border-t border-border/40">
                          <td className="px-3 py-2 font-medium text-foreground">
                            {ERROR_TYPE_LABELS[b.error_type] ?? b.error_type}
                          </td>
                          <td className="px-3 py-2 text-muted-foreground">
                            {STAGE_LABELS[b.error_stage] ?? b.error_stage}
                          </td>
                          <td className="px-3 py-2 text-right font-mono">{b.count}</td>
                          <td className="px-3 py-2 text-muted-foreground">
                            {formatRelativeTime(b.last_seen)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="rounded-md border border-dashed border-border/60 px-3 py-6 text-center text-xs text-muted-foreground">
                  <CheckCircle2 className="mx-auto mb-1 size-4 text-success" />
                  这段时间没有转写失败记录
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right column: Quota + Creators */}
        <div className="space-y-5">
          {/* Qwen quota */}
          <Card>
            <CardHeader>
              <CardTitle>Qwen 额度</CardTitle>
              <CardDescription>账号池实时额度快照</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {quota && quota.accounts.length > 0 ? (
                quota.accounts.map((acc) => (
                  <div
                    key={acc.accountId}
                    className="flex items-center justify-between rounded-[10px] border border-border/60 bg-secondary/30 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium text-foreground">
                        {acc.accountLabel}
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        {acc.status === 'active' ? '正常' : acc.status}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={cn(
                        'text-sm font-bold',
                        acc.remaining_hours <= 1 ? 'text-destructive' : acc.remaining_hours <= 3 ? 'text-warning' : 'text-success'
                      )}>
                        {acc.remaining_hours}h
                      </div>
                      <div className="text-[11px] text-muted-foreground">剩余</div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-muted-foreground">暂无账号</div>
              )}
            </CardContent>
          </Card>

          {/* Creator sync */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Users className="size-5 text-primary" />
                <CardTitle>创作者同步</CardTitle>
              </div>
              <CardDescription>自动同步状态监控</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-[10px] border border-border/60 bg-secondary/30 px-3 py-2 text-center">
                  <div className="text-lg font-bold text-foreground">{creators?.total_creators ?? 0}</div>
                  <div className="text-[11px] text-muted-foreground">创作者总数</div>
                </div>
                <div className="rounded-[10px] border border-border/60 bg-secondary/30 px-3 py-2 text-center">
                  <div className="text-lg font-bold text-foreground">{creators?.auto_sync_enabled ?? 0}</div>
                  <div className="text-[11px] text-muted-foreground">自动同步</div>
                </div>
              </div>
              {creators && creators.stale_sync_count > 0 && (
                <div className="flex items-center gap-2 rounded-[10px] border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">
                  <AlertTriangle className="size-4 shrink-0" />
                  {creators.stale_sync_count} 个创作者超过 6 小时未同步
                </div>
              )}
            </CardContent>
          </Card>

          {/* Account pool stats */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Cpu className="size-5 text-primary" />
                <CardTitle>账号池负载</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">总账号</span>
                <span className="font-medium text-foreground">{pool?.total_accounts ?? 0}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">可用</span>
                <span className="font-medium text-foreground">{pool?.available_accounts ?? 0}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">活跃上传</span>
                <span className="font-medium text-foreground">{pool?.active_uploads ?? 0}</span>
              </div>
              {pool && pool.excluded && pool.excluded.length > 0 && (
                <div className="mt-2 rounded-[10px] border border-destructive/20 bg-destructive/5 px-3 py-2">
                  <div className="text-[11px] text-destructive">
                    已排除: {pool.excluded.join(', ')}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </PageShell>
  );
}
