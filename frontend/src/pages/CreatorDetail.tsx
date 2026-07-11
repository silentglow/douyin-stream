import { ArrowLeft, RefreshCw, Loader2, X, Download, Trash2, Eye, Star, ExternalLink } from 'lucide-react';
import { AnimatePresence } from 'framer-motion';
import { TranscriptReader } from '@/components/ui/TranscriptReader';
import { cn } from '@/lib/utils';
import { Virtuoso } from 'react-virtuoso';
import { AssetListItem } from '@/components/creator/CreatorAssetList';
import { FolderBrowserModal } from '@/components/creator/FolderBrowserModal';
import { ActionMenuModal } from '@/components/creator/ActionMenuModal';
import { useCreatorDetail } from '@/hooks/useCreatorDetail';
import type { Asset } from '@/types';
import { openCreatorHomepage, resolveCreatorHomepage } from '@/lib/format';

export default function CreatorDetail() {
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
            className="h-9 w-9 rounded-lg inline-flex items-center justify-center text-[var(--color-ash)] hover:text-[var(--color-bone)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors shrink-0"
            title="返回内容库"
          >
            <ArrowLeft className="w-4 h-4" strokeWidth={2} />
          </button>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 min-w-0">
              <h1 className="text-[17px] font-semibold text-[var(--color-bone)] truncate tracking-tight">
                {isLocal ? '本地素材' : creator?.nickname ?? '创作者'}
              </h1>
              {homepageUrl && creator && (
                <button
                  type="button"
                  onClick={() => openCreatorHomepage(creator)}
                  className="shrink-0 p-1.5 rounded-md text-[var(--color-smoke)] hover:text-[var(--color-rust)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors"
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
              {failedCount > 0 && (
                <span className="text-[var(--color-iron)]"> · {failedCount} 失败</span>
              )}
            </div>
          </div>

          {!isLocal && (
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={() => handleSync('incremental')}
                disabled={syncing}
                className="h-9 px-3.5 rounded-lg text-[13px] font-medium inline-flex items-center gap-1.5 bg-[var(--color-rust)] text-white hover:brightness-110 shadow-sm disabled:opacity-50 transition-all"
                title="增量同步"
              >
                {syncing ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="w-3.5 h-3.5" strokeWidth={2} />
                )}
                同步
              </button>
              <button
                type="button"
                onClick={() => handleSync('full')}
                disabled={syncing}
                className="h-9 px-2.5 rounded-lg text-[12px] font-medium text-[var(--color-smoke)] hover:text-[var(--color-iron)] hover:bg-[rgba(239,68,68,0.08)] disabled:opacity-40 transition-colors"
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
          {([
            { key: 'all', label: '全部', count: assets.length },
            { key: 'completed', label: '已转写', count: completedCount },
            { key: 'starred', label: '收藏', count: starredCount },
            { key: 'failed', label: '失败', count: failedCount, danger: true },
          ] as const).map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTabFilter(t.key)}
              className={cn(
                'h-8 px-2.5 text-[12px] font-medium rounded-md transition-all inline-flex items-center gap-1',
                tabFilter === t.key
                  ? 'bg-[var(--color-paper)] text-[var(--color-bone)] shadow-sm'
                  : 'text-[var(--color-smoke)] hover:text-[var(--color-ash)]',
              )}
            >
              {t.label}
              <span
                className={cn(
                  'tabular-nums text-[11px]',
                  'danger' in t && t.danger && t.count > 0
                    ? 'text-[var(--color-iron)]'
                    : 'text-[var(--color-smoke)]',
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
                onClick={() => { setBulkMode(false); setSelectedAssets(new Set()); }}
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
          <div className="py-24 text-center">
            <div className="font-display text-[32px] text-[var(--color-smoke)] mb-2">
              {tabFilter === 'all' ? '还没有素材' : '此筛选下暂无内容'}
            </div>
            <div className="text-[13px] text-[var(--color-ash)]">
              {isLocal ? '在内容库点击「本地上传」添加文件' : '点击上方「同步」按钮获取视频'}
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

      {/* ═══ TRANSCRIPT READER ══════════════════════════════════ */}
      <AnimatePresence>
        {viewingAsset && (
          <TranscriptReader
            asset={viewingAsset}
            content={transcriptContent}
            loading={transcriptLoading}
            onClose={() => setViewingAsset(null)}
            onPrev={() => {
              const completed = assets.filter((a) => a.transcript_status === 'completed');
              const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id);
              if (ci > 0) { setTranscriptContent(''); setTranscriptLoading(true); handleViewTranscript(completed[ci - 1]); }
            }}
            onNext={() => {
              const completed = assets.filter((a) => a.transcript_status === 'completed');
              const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id);
              if (ci >= 0 && ci < completed.length - 1) { setTranscriptContent(''); setTranscriptLoading(true); handleViewTranscript(completed[ci + 1]); }
            }}
            hasPrev={(() => { const completed = assets.filter((a) => a.transcript_status === 'completed'); const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id); return ci > 0; })()}
            hasNext={(() => { const completed = assets.filter((a) => a.transcript_status === 'completed'); const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id); return ci >= 0 && ci < completed.length - 1; })()}
            onAssetUpdate={(updated) => { setAssets((prev: Asset[]) => prev.map((a: Asset) => a.asset_id === updated.asset_id ? updated : a)); }}
          />
        )}
      </AnimatePresence>

      <FolderBrowserModal
        isOpen={folderBrowser.open}
        assetTitle={folderBrowser.assetTitle}
        loading={folderBrowser.loading}
        data={folderBrowser.data}
        onClose={() => setFolderBrowser((prev) => ({ ...prev, open: false }))}
      />
    </div>
  );
}
