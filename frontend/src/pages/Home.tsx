import { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Play, Heart, Star, Users, Zap, Link2, Plus, FileAudio, Trash2,
  CheckCircle2, AlertTriangle, ArrowRight, Cloud,
} from 'lucide-react';
import { Widget } from '@/components/ui/Widget';
import { WidgetGrid } from '@/components/layout/WidgetGrid';
import { useStore } from '@/store/useStore';
import { getDashboard, type DashboardData } from '@/services/dashboard';
import { getFailureSummary, type FailureSummary } from '@/services/tasks';
import { getTaskDisplayState } from '@/lib/task-utils';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

/* ── 颜色精确值（对齐 prototype.html） ── */
const C = {
  blue: '#007AFF',
  green: '#34C759',
  orange: '#FF9500',
  red: '#FF3B30',
  purple: '#AF52DE',
  teal: '#5AC8FA',
  textPrimary: '#000000',
  textSecondary: '#8E8E93',
  bgWidgetSecondary: '#F2F2F7',
};

/* ── 创作者渐变 ── */
const gradients = [
  'from-[#667eea] to-[#764ba2]',
  'from-[#f093fb] to-[#f5576c]',
  'from-[#4facfe] to-[#00f2fe]',
  'from-[#43e97b] to-[#38f9d7]',
  'from-[#fa709a] to-[#fee140]',
  'from-[#a8edea] to-[#fed6e3]',
  'from-[#ff9a9e] to-[#fecfef]',
];

/* ── 小组件 ── */
function ProgressBar({ percent, color = C.blue }: { percent: number; color?: string }) {
  return (
    <div className="h-1.5 rounded-full overflow-hidden" style={{ background: C.bgWidgetSecondary }}>
      <div
        className="h-full rounded-full transition-all duration-500 ease-out"
        style={{ width: `${Math.min(percent, 100)}%`, background: color }}
      />
    </div>
  );
}

function StageIndicator({ stages, activeIndex }: { stages: string[]; activeIndex: number }) {
  return (
    <div className="flex items-center gap-1.5 mt-2">
      {stages.map((stage, i) => (
        <div key={stage} className="flex items-center gap-1.5">
          {i > 0 && (
            <div
              className="w-5 h-0.5 rounded-full"
              style={{ background: i <= activeIndex ? C.blue : C.bgWidgetSecondary }}
            />
          )}
          <div className="flex items-center gap-1">
            <div
              className="w-2 h-2 rounded-full"
              style={{ background: i <= activeIndex ? C.blue : C.bgWidgetSecondary }}
            />
            <span
              className="text-xs"
              style={{ color: i <= activeIndex ? C.blue : C.textSecondary }}
            >
              {stage}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function HealthDot({ healthy }: { healthy: boolean }) {
  const color = healthy ? C.green : C.red;
  return (
    <span
      className="inline-block w-2.5 h-2.5 rounded-full mr-2"
      style={{ background: color, boxShadow: `0 0 8px ${color}` }}
    />
  );
}

/* ── 页面 ── */
export default function Home() {
  const navigate = useNavigate();
  const tasks = useStore((s) => s.tasks);
  const creators = useStore((s) => s.creators);
  const fetchCreators = useStore((s) => s.fetchCreators);

  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [failureSummary, setFailureSummary] = useState<FailureSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [dash, fail] = await Promise.all([getDashboard(), getFailureSummary(1)]);
        if (!cancelled) {
          setDashboard(dash);
          setFailureSummary(fail);
        }
      } catch { /* ignore */ }
      finally { if (!cancelled) setLoading(false); }
    }
    load();
    fetchCreators();
    return () => { cancelled = true; };
  }, [fetchCreators]);

  /* 活跃任务 */
  const activeTasks = useMemo(() => {
    return tasks
      .filter((t) => {
        const s = getTaskDisplayState(t);
        return s === 'running' || s === 'paused';
      })
      .sort((a, b) => (b.progress || 0) - (a.progress || 0));
  }, [tasks]);

  const activeCount = activeTasks.length;

  /* 最近动态 */
  const recentActivity = useMemo(() => {
    const done = tasks
      .filter((t) => t.status === 'COMPLETED' || t.status === 'FAILED' || t.status === 'PARTIAL_FAILED')
      .sort((a, b) => (b.update_time || '').localeCompare(a.update_time || ''))
      .slice(0, 5);
    return done.map((t) => ({
      id: t.task_id,
      type: t.status === 'COMPLETED' ? 'success' : t.status === 'PARTIAL_FAILED' ? 'warning' : 'error' as const,
      text: t.task_type === 'pipeline' ? '下载完成' : t.task_type === 'transcribe' ? '转写完成' : '任务完成',
      detail: t.payload ? (() => { try { const p = JSON.parse(t.payload); return p.msg || ''; } catch { return ''; } })() : '',
      time: t.update_time ? new Date(t.update_time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '',
    }));
  }, [tasks]);

  const topTask = activeTasks[0];
  const healthHealthy = dashboard?.health?.total_anomaly_count === 0;

  const totalQuotaHours = useMemo(() => {
    if (!dashboard?.quota_status?.accounts) return 0;
    return dashboard.quota_status.accounts.reduce((sum, a) => sum + (a.remaining_hours || 0), 0);
  }, [dashboard]);

  const autoSyncCount = creators.filter((c) => c.sync_status === 'auto' || c.sync_status === 'active').length;

  /* 快捷操作 */
  const handlePasteLink = useCallback(() => {
    navigator.clipboard.readText().then((text) => {
      if (text.trim()) toast.success('已粘贴链接，跳转下载...');
      else toast.error('剪贴板为空');
    }).catch(() => toast.error('无法读取剪贴板'));
  }, []);

  if (loading) {
    return (
      <div className="h-full p-7 px-8 max-sm:p-4 max-sm:pb-20 overflow-y-auto">
        <div className="grid grid-cols-4 md:grid-cols-3 max-sm:grid-cols-2 gap-4 max-sm:gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="bg-white rounded-[22px] apple-skeleton"
              style={{
                gridColumn: i >= 6 ? 'span 4' : i >= 4 ? 'span 2' : 'span 1',
                minHeight: i >= 4 ? 180 : i >= 4 ? 160 : 140,
              }}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full p-6 max-sm:p-4 max-sm:pb-20 overflow-y-auto">
      {/* 手机2列 / 平板3列 / 桌面4列 */}
      <WidgetGrid>
        {/* ── 行1: 4个 Small ── */}
        <Widget
          size="small"
          icon={<Play className="size-4" style={{ color: C.blue }} />}
          iconBg="bg-[rgba(10,132,255,0.12)]"
          title="运行中任务"
          tint="blue"
        >
          <div className="text-[34px] font-bold tracking-tight leading-none" style={{ color: C.textPrimary }}>
            {activeCount}
          </div>
        </Widget>

        <Widget
          size="small"
          icon={<Heart className="size-4" style={{ color: C.green }} />}
          iconBg="bg-[rgba(48,209,88,0.12)]"
          title="系统状态"
          tint="green"
        >
          <div className="flex items-center text-[22px] font-semibold" style={{ color: C.textPrimary }}>
            <HealthDot healthy={healthHealthy} />
            {healthHealthy ? '正常' : `${dashboard?.health?.total_anomaly_count || 0} 个异常`}
          </div>
        </Widget>

        <Widget
          size="small"
          icon={<Star className="size-4" style={{ color: C.purple }} />}
          iconBg="bg-[rgba(175,82,222,0.12)]"
          title="Qwen 额度"
          tint="purple"
        >
          <div className="text-[34px] font-bold tracking-tight leading-none" style={{ color: C.textPrimary }}>
            {Math.round(totalQuotaHours)}h
          </div>
          <div className="text-xs mt-1" style={{ color: C.textSecondary }}>
            {(dashboard?.quota_status?.accounts?.length || 0)} 个账号可用
          </div>
        </Widget>

        <Widget
          size="small"
          icon={<Users className="size-4" style={{ color: C.orange }} />}
          iconBg="bg-[rgba(255,159,10,0.12)]"
          title="创作者"
        >
          <div className="text-[34px] font-bold tracking-tight leading-none" style={{ color: C.textPrimary }}>
            {creators.length}
          </div>
          <div className="text-xs mt-1" style={{ color: C.textSecondary }}>
            {creators.length} 个创作者 · {autoSyncCount} 个自动同步
          </div>
        </Widget>

        {/* ── 行2: Large 实时进度 ── */}
        {topTask ? (
          <Widget
            size="large"
            icon={<Zap className="size-4" style={{ color: C.blue }} />}
            iconBg="bg-[rgba(10,132,255,0.12)]"
            title="实时任务进度"
            className="bg-gradient-to-br from-white to-[rgba(10,132,255,0.04)]"
          >
            <div className="flex justify-between items-center mb-2">
              <span className="text-[17px] font-semibold truncate">
                {(() => { try { const p = JSON.parse(topTask.payload || '{}'); return p.msg || topTask.task_type || '任务'; } catch { return topTask.task_type || '任务'; } })()}
              </span>
              <span className="text-[15px] font-semibold" style={{ color: C.blue }}>
                {Math.round(topTask.progress || 0)}%
              </span>
            </div>
            <ProgressBar percent={topTask.progress || 0} />
            <div className="text-[13px] mt-1.5" style={{ color: C.textSecondary }}>
              {topTask.status === 'RUNNING' ? '运行中' : topTask.status === 'PAUSED' ? '已暂停' : topTask.status}
              {' · 预计剩余 '}4{' 分钟 · 已下载 '}12{'/'}15{' 个视频'}
            </div>
            <StageIndicator stages={['下载', '转写', '导出']} activeIndex={(() => {
              const p = topTask.progress || 0;
              if (p < 30) return 0;
              if (p < 80) return 1;
              return 2;
            })()} />
          </Widget>
        ) : (
          <Widget size="large" icon={<Cloud className="size-4 text-[#C7C7CC]" />} iconBg="bg-[#F2F2F7]" title="实时任务进度">
            <div className="flex flex-col items-center justify-center py-4 gap-3">
              <Cloud className="size-16 opacity-30" style={{ color: C.textSecondary }} />
              <div className="text-sm" style={{ color: C.textSecondary }}>系统空闲中</div>
              <button
                onClick={() => navigate('/library')}
                className="px-5 py-2 rounded-xl text-sm font-semibold text-white"
                style={{ background: C.blue }}
              >
                添加第一个创作者
              </button>
            </div>
          </Widget>
        )}

        {/* ── 行3: Medium × 2 ── */}
        <Widget
          size="medium"
          icon={<Play className="size-4" style={{ color: C.blue }} />}
          iconBg="bg-[rgba(10,132,255,0.12)]"
          title="活跃任务"
        >
          <div className="flex flex-col">
            {activeTasks.slice(0, 3).map((task) => (
              <div
                key={task.task_id}
                className="flex items-center gap-3 py-1.5"
                style={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}
              >
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: C.bgWidgetSecondary }}
                >
                  <Play className="size-4" style={{ color: C.blue }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate" style={{ color: C.textPrimary }}>
                    {(() => { try { const p = JSON.parse(task.payload || '{}'); return p.msg || task.task_type; } catch { return task.task_type; } })()}
                  </div>
                  <div className="text-xs" style={{ color: C.textSecondary }}>
                    {task.status === 'RUNNING' ? '运行中' : '已暂停'} · {Math.round(task.progress || 0)}%
                  </div>
                </div>
                <div className="w-16">
                  <ProgressBar percent={task.progress || 0} />
                </div>
              </div>
            ))}
            {activeTasks.length === 0 && (
              <div className="text-sm text-center py-4" style={{ color: C.textSecondary }}>暂无运行中任务</div>
            )}
          </div>
          {activeTasks.length > 3 && (
            <div className="text-xs mt-1" style={{ color: C.textSecondary }}>
              还有 {activeTasks.length - 3} 个任务运行中
            </div>
          )}
        </Widget>

        <Widget
          size="medium"
          icon={<CheckCircle2 className="size-4" style={{ color: C.green }} />}
          iconBg="bg-[rgba(48,209,88,0.12)]"
          title="最近动态"
        >
          <div className="flex flex-col">
            {recentActivity.slice(0, 3).map((act) => (
              <div
                key={act.id}
                className="flex items-center gap-3 py-1.5"
                style={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}
              >
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                  style={{
                    background: act.type === 'success' ? 'rgba(48,209,88,0.12)' : act.type === 'warning' ? 'rgba(255,159,10,0.12)' : 'rgba(255,69,58,0.12)',
                  }}
                >
                  {act.type === 'success'
                    ? <CheckCircle2 className="size-3.5" style={{ color: C.green }} />
                    : <AlertTriangle className="size-3.5" style={{ color: act.type === 'warning' ? C.orange : C.red }} />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate" style={{ color: C.textPrimary }}>
                    {act.text} {act.detail}
                  </div>
                </div>
                <div className="text-xs shrink-0" style={{ color: C.textSecondary }}>{act.time}</div>
              </div>
            ))}
            {recentActivity.length === 0 && (
              <div className="text-sm text-center py-4" style={{ color: C.textSecondary }}>暂无动态</div>
            )}
          </div>
          <div className="text-xs mt-1" style={{ color: C.textSecondary }}>
            过去 24 小时 {tasks.filter((t) => t.status === 'COMPLETED' || t.status === 'PARTIAL_FAILED').length} 条动态
          </div>
        </Widget>

        {/* ── 行4: Large 快捷操作 ── */}
        <Widget
          size="large"
          icon={<Plus className="size-4" style={{ color: C.blue }} />}
          iconBg="bg-[rgba(10,132,255,0.12)]"
          title="快捷操作"
        >
          <div className="flex flex-wrap gap-3">
            {[
              { icon: <Link2 className="size-4" />, label: '粘贴链接下载', onClick: handlePasteLink },
              { icon: <Plus className="size-4" />, label: '添加创作者', onClick: () => navigate('/library') },
              { icon: <FileAudio className="size-4" />, label: '本地转写', onClick: () => toast.info('本地转写功能开发中') },
              { icon: <Trash2 className="size-4" />, label: '清理历史任务', onClick: () => toast.info('清理功能开发中') },
            ].map((btn) => (
              <button
                key={btn.label}
                onClick={btn.onClick}
                className="flex items-center gap-2 px-5 py-3 rounded-xl text-[15px] font-medium transition-all active:scale-[0.96]"
                style={{ background: C.bgWidgetSecondary }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = C.blue;
                  (e.currentTarget as HTMLButtonElement).style.color = '#fff';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = C.bgWidgetSecondary;
                  (e.currentTarget as HTMLButtonElement).style.color = '';
                }}
              >
                {btn.icon}
                {btn.label}
              </button>
            ))}
          </div>
        </Widget>

        {/* ── 行5: Large 创作者概览 ── */}
        <Widget
          size="large"
          icon={<Users className="size-4" style={{ color: C.orange }} />}
          iconBg="bg-[rgba(255,159,10,0.12)]"
          title="创作者概览"
          onClick={() => navigate('/library')}
        >
          <div className="flex flex-col">
            {creators.slice(0, 3).map((creator, i) => (
              <div
                key={creator.uid}
                className="flex items-center gap-3 py-1.5"
                style={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}
              >
                <div
                  className={cn('w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold text-white shrink-0 bg-gradient-to-br', gradients[i % gradients.length])}
                >
                  {creator.nickname?.[0] || '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate" style={{ color: C.textPrimary }}>
                    {creator.nickname}
                  </div>
                  <div className="text-xs" style={{ color: C.textSecondary }}>
                    {creator.asset_count || 0} 个视频 ·
                    {creator.last_fetch_time
                      ? ` ${new Date(creator.last_fetch_time).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })} 同步`
                      : ' 未同步'}
                  </div>
                </div>
                <span className="text-xs shrink-0" style={{ color: C.textSecondary }}>
                  {creator.sync_status === 'auto' || creator.sync_status === 'active' ? '自动同步' : '手动'}
                </span>
              </div>
            ))}
            {creators.length === 0 && (
              <div className="text-sm text-center py-4" style={{ color: C.textSecondary }}>暂无创作者</div>
            )}
          </div>
          <div className="flex items-center gap-1 text-xs mt-1" style={{ color: C.textSecondary }}>
            {creators.length} 个创作者 · 查看全部
            <ArrowRight className="size-3 ml-1" />
          </div>
        </Widget>

        {/* 失败摘要（条件显示） */}
        {failureSummary && failureSummary.total_failed > 0 && (
          <Widget
            size="medium"
            icon={<AlertTriangle className="size-4" style={{ color: C.red }} />}
            iconBg="bg-[rgba(255,69,58,0.12)]"
            title="失败摘要"
            tint="red"
          >
            <div className="flex flex-col">
              {failureSummary.buckets.slice(0, 2).map((b) => (
                <div
                  key={b.error_type}
                  className="flex items-center justify-between py-1.5"
                  style={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}
                >
                  <span className="text-sm truncate" style={{ color: C.textPrimary }}>{b.error_type}</span>
                  <span className="text-sm font-semibold" style={{ color: C.red }}>{b.count}</span>
                </div>
              ))}
            </div>
            <div className="text-xs mt-1" style={{ color: C.textSecondary }}>
              过去 {failureSummary.window_days} 天共 {failureSummary.total_failed} 次失败
            </div>
          </Widget>
        )}
      </WidgetGrid>
    </div>
  );
}
