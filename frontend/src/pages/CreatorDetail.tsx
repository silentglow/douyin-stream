import { ArrowLeft, RefreshCw, Loader2, X, Download, Trash2, Eye, Star } from 'lucide-react';
import { AnimatePresence } from 'framer-motion';
import { TranscriptReader } from '@/components/ui/TranscriptReader';
import { cn } from '@/lib/utils';
import { Virtuoso } from 'react-virtuoso';
import { AssetListItem } from '@/components/creator/CreatorAssetList';
import { FolderBrowserModal } from '@/components/creator/FolderBrowserModal';
import { ActionMenuModal } from '@/components/creator/ActionMenuModal';
import { useCreatorDetail } from '@/hooks/useCreatorDetail';
import type { Asset } from '@/types';

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

  return (
    <div className="h-full flex flex-col page-enter">
      {/* ═══ MASTHEAD ═══════════════════════════════════════════ */}
      <header className="px-10 pt-10 pb-8 border-b border-[var(--color-hairline)] flex-shrink-0">
        <button
          onClick={() => navigate('/library')}
          className="flex items-center gap-2 mb-5 text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)] transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" strokeWidth={1.5} />
          返回内容库
        </button>

        <div className="flex items-end justify-between gap-10">
          <div className="flex-1 min-w-0">
            <div className="eyebrow mb-4">
              {assets.length} 个文件
              {completedCount > 0 && <span> · {completedCount} 已转写</span>}
              {starredCount > 0 && <span> · {starredCount} 收藏</span>}
              {failedCount > 0 && <span className="text-[var(--color-iron)]"> · {failedCount} 失败</span>}
            </div>
            <h1 className="font-display text-[clamp(40px,5.5vw,80px)] leading-[0.95] tracking-display text-[var(--color-bone)] truncate">
              {isLocal ? '本地素材' : creator?.nickname ?? '创作者'}
            </h1>
          </div>

          {!isLocal && (
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => handleSync('incremental')}
                disabled={syncing}
                className="btn-sharp flex items-center gap-2"
              >
                {syncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                同步
              </button>
              <button
                onClick={() => handleSync('full')}
                disabled={syncing}
                className="btn-sharp flex items-center gap-2"
                title="全量重拉（忽略本地已有，重新下载所有视频）"
              >
                全量
              </button>
            </div>
          )}
        </div>
      </header>

      {/* ═══ TABS + BULK ════════════════════════════════════════ */}
      <section className="px-10 py-4 border-b border-[var(--color-hairline)] flex-shrink-0 flex items-center justify-between gap-6">
        <div className="flex items-center gap-1">
          {([
            { key: 'all', label: '全部', count: assets.length },
            { key: 'completed', label: '已转写', count: completedCount },
            { key: 'starred', label: '收藏', count: starredCount },
            { key: 'failed', label: '失败', count: failedCount, danger: true },
          ] as const).map((t) => (
            <button
              key={t.key}
              onClick={() => setTabFilter(t.key)}
              className={cn(
                'px-3 py-1.5 text-[12px] font-medium transition-colors border-b',
                tabFilter === t.key
                  ? 'text-[var(--color-rust)] border-[var(--color-rust)]'
                  : 'text-[var(--color-smoke)] hover:text-[var(--color-bone)] border-transparent'
              )}
            >
              {t.label}
              <span className={cn(
                'ml-1.5 font-display text-[14px] tabular',
                'danger' in t && t.danger && t.count > 0 ? 'text-[var(--color-iron)]' : 'text-[var(--color-ash)]'
              )}>
                {t.count}
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          {bulkMode ? (
            <>
              <span className="text-[12px] text-[var(--color-ash)]">已选 <span className="font-display text-[16px] text-[var(--color-rust)] tabular">{selectedAssets.size}</span></span>
              <button
                onClick={handleBulkExport}
                disabled={selectedAssets.size === 0}
                className="btn-sharp disabled:opacity-40 flex items-center gap-2"
              >
                <Download className="w-3.5 h-3.5" />
                导出
              </button>
              <button
                onClick={handleBulkMarkRead}
                disabled={selectedAssets.size === 0}
                className="btn-sharp disabled:opacity-40 flex items-center gap-2"
              >
                <Eye className="w-3.5 h-3.5" />
                已读
              </button>
              <button
                onClick={handleBulkMarkStar}
                disabled={selectedAssets.size === 0}
                className="btn-sharp disabled:opacity-40 flex items-center gap-2"
              >
                <Star className="w-3.5 h-3.5" />
                收藏
              </button>
              <button
                onClick={handleBulkDelete}
                disabled={selectedAssets.size === 0}
                className="btn-sharp border-[var(--color-iron)] text-[var(--color-iron)] hover:bg-[var(--color-iron)] hover:text-[var(--color-ink)] disabled:opacity-40 flex items-center gap-2"
              >
                <Trash2 className="w-3.5 h-3.5" />
                删除
              </button>
              <button
                onClick={() => { setBulkMode(false); setSelectedAssets(new Set()); }}
                className="text-[var(--color-smoke)] hover:text-[var(--color-rust)]"
              >
                <X className="w-4 h-4" />
              </button>
            </>
          ) : assets.length > 0 && (
            <button onClick={() => setBulkMode(true)} className="draw-line text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)]">
              批量操作
            </button>
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
