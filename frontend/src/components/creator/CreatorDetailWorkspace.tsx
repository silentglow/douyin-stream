import { ArrowLeft, RefreshCw, X, Download, Trash2, Eye, Star, ExternalLink, Inbox } from 'lucide-react';
import { AnimatePresence } from 'framer-motion';
import { lazy, Suspense, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { Virtuoso } from 'react-virtuoso';
import { AssetListItem } from '@/components/creator/CreatorAssetList';

import { useCreatorDetail } from '@/hooks/useCreatorDetail';
import type { Asset } from '@/types';
import { openCreatorHomepage, resolveCreatorHomepage } from '@/lib/format';

const TranscriptReader = lazy(() =>
  import('@/components/ui/TranscriptReader').then((module) => ({ default: module.TranscriptReader })),
);
const FolderBrowserModal = lazy(() =>
  import('@/components/creator/FolderBrowserModal').then((module) => ({ default: module.FolderBrowserModal })),
);
const ActionMenuModal = lazy(() =>
  import('@/components/creator/ActionMenuModal').then((module) => ({ default: module.ActionMenuModal })),
);

export function CreatorDetailWorkspace() {
  const {
    navigate,
    assets,
    setAssets,
    loading,
    syncing,
    viewingAsset,
    setViewingAsset,
    transcriptContent,
    setTranscriptContent,
    transcriptLoading,
    setTranscriptLoading,
    selectedAssets,
    setSelectedAssets,
    actionMenuAsset,
    setActionMenuAsset,
    bulkMode,
    setBulkMode,
    tabFilter,
    setTabFilter,
    folderBrowser,
    setFolderBrowser,
    isLocal,
    creator,
    handleViewTranscript,
    handleSync,
    handleToggleStar,
    handleToggleRead,
    handleDeleteAsset,
    handleExportTranscript,
    handleViewFile,
    handleBrowseFolder,
    handleBulkExport,
    handleBulkDelete,
    handleBulkMarkRead,
    handleBulkMarkStar,
    toggleAssetSelection,
    filteredAssets,
    completedCount,
    starredCount,
    failedCount,
  } = useCreatorDetail();
  const completedAssets = useMemo(() => assets.filter((asset) => asset.transcript_status === 'completed'), [assets]);
  const viewingIndex = viewingAsset
    ? completedAssets.findIndex((asset) => asset.asset_id === viewingAsset.asset_id)
    : -1;

  if (!creator && !isLocal) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-[var(--color-smoke)]">创作者不存在</div>
      </div>
    );
  }

  const homepageUrl = !isLocal && creator ? resolveCreatorHomepage(creator) : null;

  return (
    <div className="h-full flex flex-col page-enter">
      {/* Compact masthead */}
      <header className="px-6 md:px-8 py-3.5 border-b border-[var(--color-hairline)] flex-shrink-0">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/library')}
            className="ui-press h-9 w-9 rounded-lg inline-flex items-center justify-center text-[var(--color-ash)] hover:text-[var(--color-bone)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] shrink-0"
            title="返回内容库"
          >
            <ArrowLeft className="w-4 h-4" strokeWidth={2} />
          </button>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 min-w-0">
              <h1 className="text-[17px] font-semibold text-[var(--color-bone)] truncate tracking-tight">
                {isLocal ? '本地素材' : (creator?.nickname ?? '创作者')}
              </h1>
              {homepageUrl && creator && (
                <button
                  type="button"
                  onClick={() => openCreatorHomepage(creator)}
                  className="ui-press shrink-0 p-1.5 rounded-md text-[var(--color-smoke)] hover:text-[var(--color-rust)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06]"
                  title="打开博主主页"
                >
                  <ExternalLink className="w-3.5 h-3.5" strokeWidth={2} />
                </button>
              )}
            </div>
            <div className="text-[12px] text-[var(--color-smoke)] mt-0.5 tabular-nums">
              {assets.length} 文件
              {completedCount > 0 && <span> · {completedCount} 文稿</span>}
              {starredCount > 0 && <span> · {starredCount} 收藏</span>}
              {failedCount > 0 && <span className="text-[var(--color-iron)]"> · {failedCount} 失败</span>}
            </div>
          </div>

          {!isLocal && (
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={() => handleSync('incremental')}
                disabled={syncing}
                className="ui-press h-9 px-3.5 rounded-lg text-[13px] font-medium inline-flex items-center gap-1.5 bg-[var(--color-rust)] text-white hover:brightness-110 shadow-sm shadow-[var(--color-rust)]/25 disabled:opacity-50"
                title="增量同步"
              >
                <RefreshCw className={cn('w-3.5 h-3.5', syncing && 'ui-sync-spin-loop')} strokeWidth={2} />
                同步
              </button>
              <button
                type="button"
                onClick={() => handleSync('full')}
                disabled={syncing}
                className="ui-press h-9 px-2.5 rounded-lg text-[12px] font-medium text-[var(--color-smoke)] hover:text-[var(--color-iron)] hover:bg-[rgba(239,68,68,0.08)] disabled:opacity-40"
                title="全量重拉（危险）"
              >
                全量
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Tabs + bulk — single quiet bar */}
      <section className="px-6 md:px-8 py-2 border-b border-[var(--color-hairline)] flex-shrink-0 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center p-0.5 rounded-lg bg-black/[0.03] dark:bg-white/[0.04] gap-0.5">
          {(
            [
              { key: 'all', label: '全部', count: assets.length },
              { key: 'completed', label: '已转写', count: completedCount },
              { key: 'starred', label: '收藏', count: starredCount },
              { key: 'failed', label: '失败', count: failedCount, danger: true },
            ] as const
          ).map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTabFilter(t.key)}
              data-active={tabFilter === t.key}
              className={cn(
                'ui-seg ui-press h-8 px-2.5 text-[12px] font-medium rounded-md inline-flex items-center gap-1',
                tabFilter === t.key
                  ? 'bg-[var(--color-paper)] text-[var(--color-bone)] shadow-sm'
                  : 'text-[var(--color-smoke)] hover:text-[var(--color-ash)]',
              )}
            >
              {t.label}
              <span
                className={cn(
                  'tabular-nums text-[11px]',
                  'danger' in t && t.danger && t.count > 0 ? 'text-[var(--color-iron)]' : 'text-[var(--color-smoke)]',
                )}
              >
                {t.count}
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          {bulkMode ? (
            <>
              <span className="text-[12px] text-[var(--color-ash)] mr-1">
                已选 <span className="font-semibold text-[var(--color-rust)] tabular-nums">{selectedAssets.size}</span>
              </span>
              <button
                type="button"
                onClick={handleBulkExport}
                disabled={selectedAssets.size === 0}
                className="h-8 px-2.5 rounded-lg text-[12px] font-medium inline-flex items-center gap-1 text-[var(--color-ash)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] disabled:opacity-40"
              >
                <Download className="w-3.5 h-3.5" />
                导出
              </button>
              <button
                type="button"
                onClick={handleBulkMarkRead}
                disabled={selectedAssets.size === 0}
                className="h-8 px-2.5 rounded-lg text-[12px] font-medium inline-flex items-center gap-1 text-[var(--color-ash)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] disabled:opacity-40"
              >
                <Eye className="w-3.5 h-3.5" />
                已读
              </button>
              <button
                type="button"
                onClick={handleBulkMarkStar}
                disabled={selectedAssets.size === 0}
                className="h-8 px-2.5 rounded-lg text-[12px] font-medium inline-flex items-center gap-1 text-[var(--color-ash)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] disabled:opacity-40"
              >
                <Star className="w-3.5 h-3.5" />
                收藏
              </button>
              <button
                type="button"
                onClick={handleBulkDelete}
                disabled={selectedAssets.size === 0}
                className="h-8 px-2.5 rounded-lg text-[12px] font-medium inline-flex items-center gap-1 text-[var(--color-iron)] hover:bg-[rgba(239,68,68,0.08)] disabled:opacity-40"
              >
                <Trash2 className="w-3.5 h-3.5" />
                删除
              </button>
              <button
                type="button"
                onClick={() => {
                  setBulkMode(false);
                  setSelectedAssets(new Set());
                }}
                className="h-8 w-8 rounded-lg inline-flex items-center justify-center text-[var(--color-smoke)] hover:text-[var(--color-bone)]"
              >
                <X className="w-4 h-4" />
              </button>
            </>
          ) : (
            assets.length > 0 && (
              <button
                type="button"
                onClick={() => setBulkMode(true)}
                className="h-8 px-2.5 rounded-lg text-[12px] font-medium text-[var(--color-smoke)] hover:text-[var(--color-bone)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors"
              >
                批量
              </button>
            )
          )}
        </div>
      </section>

      {/* ═══ LIST ═══════════════════════════════════════════════ */}
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <div>
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-[68px] border-b border-[var(--color-hairline-faint)] skeleton" />
            ))}
          </div>
        ) : filteredAssets.length === 0 ? (
          <div className="h-full min-h-64 flex items-center justify-center px-6">
            <div className="max-w-sm text-center rounded-2xl border border-[var(--color-hairline)] bg-[var(--color-paper)]/35 px-8 py-8">
              <div className="mx-auto mb-4 w-10 h-10 rounded-xl bg-black/[0.035] dark:bg-white/[0.05] flex items-center justify-center text-[var(--color-smoke)]">
                <Inbox className="w-5 h-5" strokeWidth={1.6} />
              </div>
              <div className="text-[15px] font-semibold text-[var(--color-bone)] mb-1.5">
                {tabFilter === 'all' ? '还没有素材' : '此筛选下暂无内容'}
              </div>
              <div className="text-[12px] leading-5 text-[var(--color-smoke)]">
                {isLocal ? '返回内容库，通过「本地上传」添加文件。' : '同步后，视频和文稿会统一显示在这里。'}
              </div>
              {!isLocal && tabFilter === 'all' && (
                <button
                  type="button"
                  onClick={() => handleSync('incremental')}
                  disabled={syncing}
                  className="ui-press mt-5 h-9 px-4 rounded-lg text-[12px] font-medium inline-flex items-center gap-1.5 bg-[var(--color-rust)] text-white disabled:opacity-50"
                >
                  <RefreshCw className={cn('w-3.5 h-3.5', syncing && 'ui-sync-spin-loop')} />
                  开始同步
                </button>
              )}
            </div>
          </div>
        ) : (
          <Virtuoso
            data={filteredAssets}
            className="h-full"
            itemContent={(_index, asset) => (
              <AssetListItem
                asset={asset}
                bulkMode={bulkMode}
                isSelected={selectedAssets.has(asset.asset_id)}
                onToggleSelect={toggleAssetSelection}
                onViewTranscript={handleViewTranscript}
                onToggleStar={handleToggleStar}
                onOpenMenu={setActionMenuAsset}
              />
            )}
          />
        )}
      </div>

      {actionMenuAsset && (
        <Suspense fallback={null}>
          <ActionMenuModal
            asset={actionMenuAsset}
            onClose={() => setActionMenuAsset(null)}
            onViewTranscript={handleViewTranscript}
            onToggleRead={handleToggleRead}
            onToggleStar={handleToggleStar}
            onExportTranscript={handleExportTranscript}
            onViewFile={handleViewFile}
            onBrowseFolder={handleBrowseFolder}
            onDeleteAsset={handleDeleteAsset}
          />
        </Suspense>
      )}

      {/* ═══ TRANSCRIPT READER ══════════════════════════════════ */}
      <AnimatePresence>
        {viewingAsset && (
          <Suspense fallback={<div className="fixed inset-0 z-50 bg-[var(--color-ink)] skeleton" />}>
            <TranscriptReader
              asset={viewingAsset}
              content={transcriptContent}
              loading={transcriptLoading}
              onClose={() => setViewingAsset(null)}
              onPrev={() => {
                if (viewingIndex > 0) {
                  setTranscriptContent('');
                  setTranscriptLoading(true);
                  handleViewTranscript(completedAssets[viewingIndex - 1]);
                }
              }}
              onNext={() => {
                if (viewingIndex >= 0 && viewingIndex < completedAssets.length - 1) {
                  setTranscriptContent('');
                  setTranscriptLoading(true);
                  handleViewTranscript(completedAssets[viewingIndex + 1]);
                }
              }}
              hasPrev={viewingIndex > 0}
              hasNext={viewingIndex >= 0 && viewingIndex < completedAssets.length - 1}
              onAssetUpdate={(updated) => {
                setAssets((prev: Asset[]) => prev.map((a: Asset) => (a.asset_id === updated.asset_id ? updated : a)));
              }}
            />
          </Suspense>
        )}
      </AnimatePresence>

      {folderBrowser.open && (
        <Suspense fallback={null}>
          <FolderBrowserModal
            isOpen={folderBrowser.open}
            assetTitle={folderBrowser.assetTitle}
            loading={folderBrowser.loading}
            data={folderBrowser.data}
            onClose={() => setFolderBrowser((prev) => ({ ...prev, open: false }))}
          />
        </Suspense>
      )}
    </div>
  );
}
