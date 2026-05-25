import { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { useStore } from '@/store/useStore';
import { getDashboard, type DashboardData } from '@/services/dashboard';
import { getFailureSummary, type FailureSummary } from '@/services/tasks';
import { getQwenStatus, triggerPipeline, getTranscripts } from '@/lib/api';
import type { Asset } from '@/lib/api';
import { toast } from 'sonner';
import { HeroCol, LedgerEntry, ActionRow } from '@/components/home/HomeWidgets';
import { FailureSummarySection, RecentTranscriptsSection } from '@/components/home/HomeSections';

type LayoutContext = { setTaskDrawerOpen: (open: boolean) => void };

export default function Home() {
  const navigate = useNavigate();
  const { setTaskDrawerOpen } = useOutletContext<LayoutContext>();
  const tasks = useStore((s) => s.tasks);
  const creators = useStore((s) => s.creators);
  const fetchCreators = useStore((s) => s.fetchCreators);
  const lastCompletedTaskTime = useStore((s) => s.lastCompletedTaskTime);

  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [failureSummary, setFailureSummary] = useState<FailureSummary | null>(null);
  const [recentTranscripts, setRecentTranscripts] = useState<Asset[]>([]);
  const [qwenAccounts, setQwenAccounts] = useState<Array<{ account_id?: string; accountId?: string; remaining_hours: number }>>([]);
  const [loading, setLoading] = useState(true);

  const refreshDashboard = useCallback(async () => {
    try {
      const [dash, fail, transcripts] = await Promise.all([
        getDashboard(),
        getFailureSummary(1),
        getTranscripts('all', 4),
      ]);
      setDashboard(dash);
      setFailureSummary(fail);
      setRecentTranscripts(transcripts.items || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      await refreshDashboard();
      fetchCreators();
      getQwenStatus()
        .then((res) => { if (!cancelled) setQwenAccounts(res.accounts || []); })
        .catch(() => { /* ignore */ });
    }
    load();
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        refreshDashboard();
        getQwenStatus().then((res) => setQwenAccounts(res.accounts || [])).catch(() => { });
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => { cancelled = true; document.removeEventListener('visibilitychange', onVisible); };
  }, [fetchCreators, refreshDashboard]);

  useEffect(() => {
    if (lastCompletedTaskTime > 0) {
      refreshDashboard();
      fetchCreators();
    }
  }, [lastCompletedTaskTime, refreshDashboard, fetchCreators]);

  const recentActivity = useMemo(() => {
    const done = tasks
      .filter((t) => t.status === 'COMPLETED' || t.status === 'FAILED' || t.status === 'PARTIAL_FAILED')
      .sort((a, b) => (b.update_time || '').localeCompare(a.update_time || ''))
      .slice(0, 6);
    return done.map((t) => ({
      id: t.task_id,
      status: (t.status === 'COMPLETED' ? 'ok' : t.status === 'PARTIAL_FAILED' ? 'warn' : 'err') as 'ok' | 'warn' | 'err',
      kind: t.task_type === 'pipeline' ? '下载并转写'
        : t.task_type === 'transcribe' ? '转写'
        : t.task_type === 'creator_sync_full' ? '创作者同步'
        : (t.task_type || '任务'),
      title: t.payload ? (() => { try { const p = JSON.parse(t.payload); return p.msg || ''; } catch { return ''; } })() : '',
      when: t.update_time
        ? new Date(t.update_time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
        : '',
    }));
  }, [tasks]);

  const healthHealthy = dashboard?.health?.total_anomaly_count === 0;
  const autoSyncCount = creators.filter((c) => c.sync_status === 'auto' || c.sync_status === 'active').length;
  const totalVideos = creators.reduce((s, c) => s + (c.asset_count || 0), 0);
  const totalTranscripts = creators.reduce((s, c) => s + (c.transcript_completed_count || 0), 0);
  const totalUnread = creators.reduce((s, c) => s + (c.unread_completed_count || 0), 0);

  const handlePasteLink = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      const url = text.trim();
      if (!url) { toast.error('剪贴板为空'); return; }
      if (!url.startsWith('http')) { toast.error('剪贴板内容不是有效链接'); return; }
      toast.info('正在创建任务⋯');
      const result = await triggerPipeline(url);
      toast.success('任务已派发', { description: `id: ${result.task_id.slice(0, 8)}` });
    } catch {
      toast.error('创建任务失败');
    }
  }, []);

  const qwenTotal = qwenAccounts.reduce((s, a) => s + (a.remaining_hours || 0), 0);

  if (loading) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="px-10 pt-12 pb-9 border-b border-[var(--color-hairline)]">
          <div className="h-20 skeleton mb-4" />
        </div>
        <div className="px-10 py-10">
          <div className="grid grid-cols-4 gap-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-28 skeleton" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto page-enter">
      {/* ═══ MASTHEAD ═══════════════════════════════════════════ */}
      <header className="px-10 pt-12 pb-9 border-b border-[var(--color-hairline)]">
        <div className="flex items-end justify-between gap-10">
          <div>
            <div className="flex items-center gap-2 mb-4">
              <span className={`status-dot ${healthHealthy ? 'bg-[var(--color-patina)]' : 'bg-[var(--color-iron)]'}`} />
              <span className="eyebrow">
                {healthHealthy ? '系统正常' : `${dashboard?.health?.total_anomaly_count || 0} 项异常`}
              </span>
            </div>
            <h1 className="font-display text-[clamp(48px,6.5vw,96px)] leading-[0.95] tracking-display text-[var(--color-bone)]">
              工作台
            </h1>
            <p className="mt-4 text-[15px] leading-[1.55] text-[var(--color-ash)] max-w-xl">
              {creators.length > 0 ? (
                <>
                  你正在监管{' '}
                  <span className="text-[var(--color-bone)]">{creators.length}</span>{' '}
                  位创作者，<span className="text-[var(--color-bone)]">{totalVideos}</span>{' '}
                  段影像在册{totalUnread > 0 && <>，<span className="text-[var(--color-rust)]">{totalUnread}</span> 篇文稿待阅</>}。
                </>
              ) : (
                <>空白的工作台。点选「新建任务」收录第一位创作者。</>
              )}
            </p>
          </div>

          <button onClick={() => navigate('/discover')} className="btn-sharp btn-primary">
            + 新建任务
          </button>
        </div>
      </header>

      {/* ═══ HERO STATS ═════════════════════════════════════════ */}
      <section className="px-10 py-10 border-b border-[var(--color-hairline)]">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 stagger">
          <HeroCol label="创作者" value={creators.length} sub={`${autoSyncCount} 个自动同步`} />
          <HeroCol label="视频" value={totalVideos} sub={`${totalTranscripts} 段已转写`} />
          <HeroCol label="文稿" value={totalTranscripts} sub={totalUnread > 0 ? `${totalUnread} 篇待阅` : '全部已读'} accent={totalUnread > 0} />
          <HeroCol label="Qwen 额度" value={Math.round(qwenTotal)} unit="hr" sub={`${qwenAccounts.length} 个账户`} />
        </div>
      </section>

      {/* ═══ TWO-COLUMN BODY ════════════════════════════════════ */}
      <section className="px-10 py-12 grid grid-cols-[1.6fr_1fr] gap-12 border-b border-[var(--color-hairline)]">
        {/* LEFT — Activity ledger */}
        <div className="bloom-enter">
          <div className="flex items-baseline justify-between mb-5 pb-3 border-b border-[var(--color-hairline-strong)]">
            <h2 className="font-display text-[28px] text-[var(--color-bone)] leading-none">最近动态</h2>
            <button
              onClick={() => setTaskDrawerOpen(true)}
              className="draw-line text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)] transition-colors"
            >
              查看全部 →
            </button>
          </div>

          {recentActivity.length === 0 ? (
            <div className="py-16 text-center">
              <div className="font-display text-[22px] text-[var(--color-smoke)]">
                队列暂时安静
              </div>
            </div>
          ) : (
            <div>
              {recentActivity.map((act) => (
                <LedgerEntry
                  key={act.id}
                  when={act.when}
                  kind={act.kind}
                  title={act.title || '⸺'}
                  status={act.status}
                />
              ))}
            </div>
          )}
        </div>

        {/* RIGHT — Action manifest */}
        <div className="bloom-enter">
          <div className="flex items-baseline justify-between mb-5 pb-3 border-b border-[var(--color-hairline-strong)]">
            <h2 className="font-display text-[28px] text-[var(--color-bone)] leading-none">快捷操作</h2>
          </div>

          <div>
            <ActionRow label="粘贴链接下载" onClick={handlePasteLink} />
            <ActionRow label="添加创作者" onClick={() => navigate('/library')} />
            <ActionRow label="本地文件转写" onClick={() => navigate('/library')} />
            <ActionRow label="发现新内容" kbd="⌘4" onClick={() => navigate('/discover')} />
          </div>
        </div>
      </section>

      {/* ═══ CREATOR ROSTER ═════════════════════════════════════ */}
      <section className="px-10 py-12 border-b border-[var(--color-hairline)]">
        <div className="flex items-baseline justify-between mb-7 pb-3 border-b border-[var(--color-hairline-strong)]">
          <h2 className="font-display text-[28px] text-[var(--color-bone)] leading-none">创作者</h2>
          <button
            onClick={() => navigate('/library')}
            className="draw-line text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)] transition-colors"
          >
            进入内容库 →
          </button>
        </div>

        {creators.length === 0 ? (
          <div className="py-16 text-center">
            <div className="font-display text-[24px] text-[var(--color-smoke)] mb-4">
              名册暂为空
            </div>
            <button onClick={() => navigate('/library')} className="btn-sharp btn-primary">
              + 添加首位创作者
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5 stagger">
            {creators.slice(0, 8).map((creator) => (
              <button
                key={creator.uid}
                onClick={() => navigate(`/library/${encodeURIComponent(creator.uid)}`)}
                className="ed-card p-5 text-left group flex flex-col justify-between min-h-[160px] cursor-pointer"
              >
                <div className="w-full">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[10px] font-bold tracking-widest text-[var(--color-smoke)] uppercase">
                      #{creator.uid.slice(0, 6)}
                    </span>
                    <span className={`text-[10.5px] font-semibold tracking-wider px-2 py-0.5 rounded-full ${
                      creator.auto_sync ? 'text-[var(--color-rust)] bg-[rgba(99,102,241,0.08)]' : 'text-[var(--color-smoke)] bg-white/5'
                    }`}>
                      {creator.auto_sync ? '自动' : '手动'}
                    </span>
                  </div>
                  <div className="font-sans font-semibold text-[17px] text-[var(--color-bone)] leading-snug group-hover:text-[var(--color-rust)] transition-colors line-clamp-2">
                    {creator.nickname || '未命名'}
                  </div>
                </div>
                <div className="mt-4 pt-3 border-t border-[var(--color-hairline-faint)] flex items-baseline justify-between">
                  <span className="text-[12.5px] text-[var(--color-ash)]">
                    <span className="font-sans font-bold text-[16px] text-[var(--color-bone)] mr-1 tabular">{creator.asset_count || 0}</span>
                    视频
                  </span>
                  <span className="text-[12.5px] text-[var(--color-ash)]">
                    <span className="font-sans font-bold text-[16px] text-[var(--color-rust)] mr-1 tabular">{creator.transcript_completed_count || 0}</span>
                    文稿
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>
      <FailureSummarySection failureSummary={failureSummary} />
      <RecentTranscriptsSection
        recentTranscripts={recentTranscripts}
        onNavigateToTranscripts={() => navigate('/transcripts')}
      />
    </div>
  );
}
