import { useEffect, useMemo, useState, useCallback } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Users, Video, FileText, Sparkles, Link as LinkIcon, UserPlus, FileUp, Plus } from 'lucide-react';
import { useStore } from '@/store/useStore';
import { getDashboard, type DashboardData } from '@/services/dashboard';
import { getFailureSummary, type FailureSummary } from '@/services/tasks';
import { getQwenStatus, triggerPipeline, addCreator, selectFolder, scanDirectory, triggerLocalTranscribe } from '@/lib/api';
import { toast } from 'sonner';
import { LedgerEntry, ActionRow } from '@/components/home/HomeWidgets';
import { FailureSummarySection } from '@/components/home/HomeSections';
import '@/components/home/home.css';

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

  const [qwenAccounts, setQwenAccounts] = useState<Array<{ account_id?: string; remaining_hours: number }>>([]);
  const [loading, setLoading] = useState(true);

  const refreshDashboard = useCallback(async () => {
    try {
      const [dash, fail] = await Promise.all([
        getDashboard(),
        getFailureSummary(1),
      ]);
      setDashboard(dash);
      setFailureSummary(fail);
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
        getQwenStatus().then((res) => { if (!cancelled) setQwenAccounts(res.accounts || []); }).catch(() => { });
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
  const totalVideos = creators.reduce((s, c) => s + (c.asset_count || 0), 0);
  const totalTranscripts = creators.reduce((s, c) => s + (c.transcript_completed_count || 0), 0);
  const totalUnread = creators.reduce((s, c) => s + (c.unread_completed_count || 0), 0);

  const handlePasteLink = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      const url = text.trim();
      if (!url) { toast.error('剪贴板为空'); return; }
      if (!url.startsWith('http')) { toast.error('剪贴板内容不是有效链接'); return; }
      toast.info('正在创建下载任务⋯');
      const result = await triggerPipeline(url);
      toast.success('下载任务已极速下发', { description: `id: ${result.task_id.slice(0, 8)}` });
    } catch {
      toast.error('创建任务失败');
    }
  }, []);

  const handleAddCreator = useCallback(async () => {
    const url = window.prompt('请输入创作者的主页链接：');
    if (!url || !url.trim()) return;
    toast.info('正在收录创作者⋯');
    try {
      await addCreator(url.trim());
      toast.success('创作者已收录', { description: '系统已在后台开始同步' });
      fetchCreators();
    } catch {
      toast.error('收录失败，请检查链接或网络状态');
    }
  }, [fetchCreators]);

  const handleLocalUpload = useCallback(async () => {
    try {
      toast.info('请在弹出的系统窗口中选择文件夹');
      const { directory } = await selectFolder();
      if (!directory) return;
      toast.info('正在扫描本地文件夹...');
      const { files } = await scanDirectory(directory);
      if (files.length === 0) {
        toast.error('未找到支持的媒体文件');
        return;
      }
      const paths = files.map((f: any) => f.path);
      toast.info(`发现 ${paths.length} 个文件，正在极速下发任务...`);
      await triggerLocalTranscribe(paths, true, directory);
      toast.success('本地转写任务已全部下发！');
      refreshDashboard();
    } catch (err: any) {
      if (err?.message !== 'cancelled') {
        toast.error('文件夹扫描或任务下发失败');
      }
    }
  }, [refreshDashboard]);

  const qwenTotal = qwenAccounts.reduce((s, a) => s + (a.remaining_hours || 0), 0);
  if (loading) {
    return (
      <div className="home-v2 h-full overflow-y-auto">
        <div className="home-aurora" />
        <div className="home-content px-6 md:px-10 pt-12 pb-9">
          <div className="h-8 w-56 skeleton rounded-xl mb-5" />
          <div className="h-20 skeleton rounded-2xl mb-10" />
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-[150px] skeleton rounded-[20px]" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="home-v2 h-full overflow-y-auto">
      <div className="home-aurora" />
      <div className="home-content">
        {/* ═══ METRIC STRIP & MASTHEAD ═══════════════════════════════════════════ */}
        <header className="px-6 md:px-10 pt-8 pb-4 border-b border-[var(--color-hairline-faint)] sticky top-0 z-10 backdrop-blur-md bg-[var(--background)]/60">
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: 'spring', stiffness: 260, damping: 24 }}
            className="flex items-center justify-between gap-8 flex-wrap"
          >
            <div className="flex items-center gap-6">
              <h1 className="font-sans text-[20px] font-bold text-[var(--home-fg)]">
                工作台
              </h1>
              <div className="h-5 w-[1px] bg-[var(--color-hairline-strong)]" />
              <div className="flex items-center gap-6 text-[13px] text-[var(--home-fg-soft)] font-medium tabular">
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4 text-[var(--home-fg-muted)]" strokeWidth={2} />
                  <span className="text-[var(--home-fg)] font-semibold">{creators.length}</span> 创作者
                </div>
                <div className="flex items-center gap-2">
                  <Video className="w-4 h-4 text-[var(--home-fg-muted)]" strokeWidth={2} />
                  <span className="text-[var(--home-fg)] font-semibold">{totalVideos}</span> 影像
                </div>
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-[var(--home-fg-muted)]" strokeWidth={2} />
                  <span className={totalUnread > 0 ? 'text-[var(--color-rust)] font-bold' : 'text-[var(--home-fg)] font-semibold'}>{totalTranscripts}</span> 文稿
                </div>
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-[var(--home-fg-muted)]" strokeWidth={2} />
                  <span className="text-[var(--home-fg)] font-semibold">{Math.round(qwenTotal)}hr</span> 额度
                </div>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <span className={`home-pill ${healthHealthy ? 'home-pill-ok' : 'home-pill-err'} scale-[0.85] origin-right mr-1`}>
                <span className="home-pill-dot" />
                {healthHealthy ? '系统正常' : `${dashboard?.health?.total_anomaly_count || 0} 异常`}
              </span>
              <button onClick={() => navigate('/library')} className="home-grad-btn py-1.5 px-4 text-[13px]">
                <Plus className="w-3.5 h-3.5" strokeWidth={2.5} />
                新建
              </button>
            </div>
          </motion.div>
        </header>

        {creators.length === 0 ? (
          <section className="px-6 md:px-10 py-12 flex items-center justify-center min-h-[60vh]">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ type: 'spring', stiffness: 260, damping: 24, delay: 0.1 }}
              className="home-glass p-12 flex flex-col items-center justify-center max-w-lg w-full text-center"
            >
              <div className="w-20 h-20 bg-black/5 dark:bg-white/10 rounded-[20px] flex items-center justify-center shadow-sm border border-[var(--color-hairline-strong)] mb-6">
                <Video className="w-8 h-8 text-[var(--home-fg-muted)]" strokeWidth={1.5} />
              </div>
              <h2 className="text-[22px] font-sans font-bold text-[var(--home-fg)] mb-3">
                欢迎来到指挥中心
              </h2>
              <p className="text-[15px] text-[var(--home-fg-soft)] mb-8 leading-relaxed">
                您的工作台已就绪。请前往内容库收录第一位创作者，系统将自动开始为您追踪视频资产并生成极致精准的 AI 转写文稿。
              </p>
              <button onClick={() => navigate('/library')} className="home-grad-btn py-3 px-8 text-[15px] font-medium w-full shadow-md hover:shadow-lg transition-shadow justify-center">
                <Plus className="w-4 h-4" strokeWidth={2.5} />
                前往内容库
              </button>
            </motion.div>
          </section>
        ) : (
          <>
            {/* ═══ BENTO BOX GRID ════════════════════════════════════ */}
            <section className="px-6 md:px-10 py-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              
              {/* Box 1：任务中枢 (占据2列) */}
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ type: 'spring', stiffness: 260, damping: 24, delay: 0.1 }}
                className="home-glass p-6 flex flex-col lg:col-span-2 min-h-[380px]"
              >
                <div className="home-card-head mb-4">
                  <h2 className="home-card-title">实时任务流</h2>
                  <button onClick={() => setTaskDrawerOpen(true)} className="home-ghost-btn">
                    管理全部 →
                  </button>
                </div>

                {recentActivity.length === 0 ? (
                  <div className="flex-grow py-14 flex flex-col items-center justify-center">
                    <div className="text-[15px] text-[var(--home-fg-muted)] font-medium">
                      队列暂时安静
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-1.5 overflow-y-auto">
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
              </motion.div>

              {/* 右侧小组件列 */}
              <div className="flex flex-col gap-5 lg:col-span-1">
                {/* Box 2：真·快捷操作 */}
                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ type: 'spring', stiffness: 260, damping: 24, delay: 0.15 }}
                  className="home-glass p-6 h-fit"
                >
                  <div className="home-card-head mb-3">
                    <h2 className="home-card-title">快捷控制</h2>
                  </div>

                  <div className="flex flex-col gap-2">
                    <ActionRow label="粘贴链接急速下载" onClick={handlePasteLink} icon={<LinkIcon className="w-4 h-4" strokeWidth={2} />} />
                    <ActionRow label="输入主页收录创作者" onClick={handleAddCreator} icon={<UserPlus className="w-4 h-4" strokeWidth={2} />} />
                    <ActionRow label="唤起本地文件上传" onClick={handleLocalUpload} icon={<FileUp className="w-4 h-4" strokeWidth={2} />} />
                  </div>
                </motion.div>

                {/* Box 3：系统监控 */}
                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ type: 'spring', stiffness: 260, damping: 24, delay: 0.2 }}
                  className="home-glass p-6 flex-grow flex flex-col justify-center"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-[12px] font-medium text-[var(--home-fg-muted)] mb-1 uppercase tracking-wider">AI 算力额度</div>
                      <div className="text-[32px] font-sans font-bold text-[var(--home-fg)] leading-none tabular">
                        {Math.round(qwenTotal)}<span className="text-[16px] text-[var(--home-fg-soft)] ml-1">hr</span>
                      </div>
                    </div>
                    <div className="w-14 h-14 rounded-full border-[5px] border-[var(--color-rust)] border-opacity-90 flex items-center justify-center shadow-inner">
                      <Sparkles className="w-6 h-6 text-[var(--color-rust)]" strokeWidth={2} />
                    </div>
                  </div>
                </motion.div>
              </div>
            </section>

            {/* Box 4: 异常预警 */}
            <FailureSummarySection failureSummary={failureSummary} />
          </>
        )}
      </div>
    </div>
  );
}
