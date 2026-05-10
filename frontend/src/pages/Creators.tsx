import { useMemo, useCallback, useState } from 'react';
import { Users } from 'lucide-react';
import { useStore } from '@/store/useStore';
import { sortTasks } from '@/lib/task-utils';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { PageHeader } from '@/components/ui/PageHeader';
import { AppleEmptyState } from '@/components/ui/AppleEmptyState';
import { PageShell } from '@/components/layout/PageShell';
import { CreatorCard } from './Creators/sections/CreatorCard';
import { AddCreatorForm } from './Creators/sections/AddCreatorForm';
import { SyncSection } from './Creators/sections/SyncSection';
import { CreatorSkeleton } from './Creators/sections/CreatorSkeleton';
import { useCreatorsActions } from './Creators/useCreatorsActions';

export default function Creators() {
  const settings = useStore((state) => state.settings);
  const rawTasks = useStore((state) => state.tasks);
  const lastCompletedTaskTime = useStore((state) => state.lastCompletedTaskTime);
  const allCreators = useStore((state) => state.creators);
  const storeFetchCreators = useStore((state) => state.fetchCreators);
  const fetchInitialTasks = useStore((state) => state.fetchInitialTasks);
  const tasks = useMemo(() => sortTasks(rawTasks), [rawTasks]);
  const creators = useMemo(
    () => allCreators.filter((c) => c.platform !== 'local' && !c.uid.startsWith('local:')),
    [allCreators]
  );

  const douyinReady = settings?.status_summary.douyin_ready ?? false;
  const bilibiliReady = (settings?.status_summary.bilibili_accounts_count ?? 0) > 0;
  const canDownloadAny = settings?.status_summary.can_download ?? false;
  const qwenReady = settings?.status_summary.qwen_ready ?? false;
  const autoTranscribe = settings?.global_settings.auto_transcribe ?? false;

  const [deleteAfterTranscribe, setDeleteAfterTranscribe] = useState(true);

  const {
    loading,
    downloadingCreators,
    confirmDelete,
    deletingUids,
    transcribingUids,
    retryingFailedUids,
    newCreatorUrl,
    isAdding,
    scheduleTask,
    setNewCreatorUrl,
    setConfirmDelete,
    handleAddCreator,
    handleUnfollow,
    handleDownload,
    handleTranscribe,
    handleRetryFailed,
    handleFullSyncNow,
    handleToggleSchedule,
  } = useCreatorsActions({
    storeFetchCreators,
    fetchInitialTasks,
    lastCompletedTaskTime,
  });

  const handleDelete = useCallback((uid: string) => {
    const creator = allCreators.find(c => c.uid === uid);
    setConfirmDelete({ uid, nickname: creator?.nickname || uid });
  }, [allCreators, setConfirmDelete]);

  const summary = useMemo(() => {
    const assetCount = creators.reduce((total, c) => total + (c.disk_asset_count ?? 0), 0);
    const transcriptCount = creators.reduce((total, c) => total + (c.disk_transcript_completed_count ?? 0), 0);
    return { creators: creators.length, assets: assetCount, transcripts: transcriptCount };
  }, [creators]);

  return (
    <PageShell variant="default">
      <div className="flex flex-col gap-8">
        <PageHeader
          title="创作者"
          description="添加创作者、发起同步、管理关注列表。"
          actions={(
            <div className="flex items-end gap-6">
              <div className="text-sm text-muted-foreground">
                <div className="text-xs">创作者</div>
                <div className="mt-1 text-2xl font-bold text-foreground tabular-nums">{summary.creators}</div>
              </div>
              <div className="text-sm text-muted-foreground">
                <div className="text-xs">素材</div>
                <div className="mt-1 text-2xl font-bold text-foreground tabular-nums">{summary.assets}</div>
              </div>
              <div className="text-sm text-muted-foreground">
                <div className="text-xs">已转写</div>
                <div className="mt-1 text-2xl font-bold text-foreground tabular-nums">{summary.transcripts}</div>
              </div>
            </div>
          )}
        />

        <AddCreatorForm
          newCreatorUrl={newCreatorUrl}
          setNewCreatorUrl={setNewCreatorUrl}
          isAdding={isAdding}
          onSubmit={handleAddCreator}
          canDownloadAny={canDownloadAny}
          autoTranscribe={autoTranscribe}
          qwenReady={qwenReady}
          douyinReady={douyinReady}
          bilibiliReady={bilibiliReady}
        />

        <SyncSection
          scheduleTask={scheduleTask}
          onToggle={handleToggleSchedule}
          onFullSync={handleFullSyncNow}
          douyinReady={douyinReady}
        />

        {loading ? (
          <CreatorSkeleton />
        ) : creators.length === 0 ? (
          <div className="w-full">
            <AppleEmptyState
              icon={<Users className="size-8 stroke-[1.5]" />}
              title="还没有创作者"
              description="去设置页配置抖音 / B站账号后，在上方输入框粘贴主页链接添加创作者。"
            />
          </div>
        ) : (
          <section className="w-full grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
            {creators.map((creator) => (
              <CreatorCard
                key={creator.uid}
                creator={creator}
                tasks={tasks}
                downloadingCreators={downloadingCreators}
                isDeleting={deletingUids.has(creator.uid)}
                onDownload={handleDownload}
                onTranscribe={handleTranscribe}
                transcribingUids={transcribingUids}
                onRetryFailed={handleRetryFailed}
                retryingFailedUids={retryingFailedUids}
                onDelete={handleDelete}
                settings={settings}
                deleteAfterTranscribe={deleteAfterTranscribe}
                setDeleteAfterTranscribe={setDeleteAfterTranscribe}
              />
            ))}
          </section>
        )}

        <ConfirmDialog
          open={!!confirmDelete}
          onOpenChange={(open) => { if (!open) setConfirmDelete(null); }}
          title="删除创作者"
          description={`确定要删除「${confirmDelete?.nickname}」以及全部关联素材吗？此操作不可撤销。`}
          confirmLabel="删除"
          destructive
          onConfirm={() => {
            if (confirmDelete) void handleUnfollow(confirmDelete.uid);
          }}
        />
      </div>
    </PageShell>
  );
}
