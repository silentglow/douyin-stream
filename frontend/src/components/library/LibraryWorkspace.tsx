import {
  Search, Loader2, X, ArrowRight, Plus, Upload, MoreHorizontal,
  Archive, Trash2, RefreshCw,
} from 'lucide-react';
import { useLibraryDetail } from '@/hooks/useLibraryDetail';
import { cn } from '@/lib/utils';
import { CreatorListHeader, CreatorRow } from '@/components/library/CreatorRow';
import { CreatorScout } from '@/components/library/CreatorScout';
import { CreatorActionMenuModal } from '@/components/library/CreatorActionMenuModal';
import { DeleteConfirmModal } from '@/components/library/DeleteConfirmModal';
import { LocalTranscribeModal } from '@/components/library/LocalTranscribeModal';
import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'following', label: '跟进中' },
  { key: 'unfollowed', label: '已停跟' },
  { key: 'auto', label: '自动' },
  { key: 'transcript', label: '有文稿' },
] as const;

export function LibraryWorkspace() {
  const {
    navigate,
    allCreators,
    creators,
    hasLocalAssets,
    localAssetCount,
    filter,
    setFilter,
    search,
    setSearch,
    loading,
    syncingIds,
    deletingIds,
    actionMenuCreator,
    setActionMenuCreator,
    localTranscribeOpen,
    setLocalTranscribeOpen,
    scanning,
    scannedFiles,
    selectedFiles,
    setSelectedFiles,
    transcribing,
    deleteAfter,
    toggleDeleteAfter,
    removeDialog,
    setRemoveDialog,
    selectedUids,
    bulkBusy,
    allFilteredSelected,
    someFilteredSelected,
    filteredCreators,
    handleSync,
    handleDeleteCreator,
    executeRemove,
    openBulkRemove,
    toggleSelectUid,
    clearSelection,
    toggleSelectAllFiltered,
    handleBulkSetAutoOnSelection,
    handleBulkSyncSelection,
    handleToggleAutoSync,
    handleRefollow,
    handleBulkAutoSync,
    handleSelectFolder,
    toggleFileSelection,
    handleStartLocalTranscribe,
    totalAssets,
    totalTranscribed,
    autoCount,
  } = useLibraryDetail();

  const [scoutOpen, setScoutOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);
  const selectedCount = selectedUids.size;

  useEffect(() => {
    if (!moreOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [moreOpen]);

  return (
    <div className="h-full overflow-y-auto page-enter">
      <header className="px-6 md:px-8 py-3.5 border-b border-[var(--color-hairline)] sticky top-0 z-10 backdrop-blur-xl bg-[var(--color-ink)]/85">
        <div className="flex items-center gap-4">
          <div className="flex items-baseline gap-3 min-w-0 shrink-0">
            <h1 className="text-[17px] font-semibold text-[var(--color-bone)] tracking-tight">
              内容库
            </h1>
            <span className="hidden sm:inline text-[12px] text-[var(--color-smoke)] tabular-nums">
              {creators.length} 人 · {totalAssets} 收录 · {totalTranscribed} 文稿
              {autoCount > 0 && (
                <span className="text-[var(--color-rust)]"> · {autoCount} 自动</span>
              )}
            </span>
          </div>

          <div className="flex-1" />

          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={handleSelectFolder}
              disabled={scanning}
              className="h-9 px-3 rounded-lg text-[13px] font-medium inline-flex items-center gap-1.5 text-[var(--color-ash)] hover:text-[var(--color-bone)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors disabled:opacity-40"
            >
              {scanning ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Upload className="w-3.5 h-3.5" strokeWidth={2} />
              )}
              <span className="hidden sm:inline">本地上传</span>
            </button>

            <div className="relative" ref={moreRef}>
              <button
                type="button"
                onClick={() => setMoreOpen((v) => !v)}
                className="h-9 w-9 rounded-lg inline-flex items-center justify-center text-[var(--color-ash)] hover:text-[var(--color-bone)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors"
                title="全局操作"
              >
                <MoreHorizontal className="w-4 h-4" />
              </button>
              {moreOpen && (
                <div className="absolute right-0 top-full mt-1.5 w-56 rounded-xl border border-[var(--color-hairline)] bg-[var(--color-paper)] shadow-lg py-1 z-30">
                  <button
                    type="button"
                    disabled={creators.length === 0 || autoCount >= creators.length}
                    className="w-full px-3.5 py-2.5 text-left text-[13px] text-[var(--color-bone)] hover:bg-black/[0.03] dark:hover:bg-white/[0.04] disabled:opacity-40"
                    onClick={() => {
                      setMoreOpen(false);
                      void handleBulkAutoSync(true);
                    }}
                  >
                    全部开启自动跟进
                  </button>
                  <button
                    type="button"
                    disabled={autoCount === 0}
                    className="w-full px-3.5 py-2.5 text-left text-[13px] text-[var(--color-bone)] hover:bg-black/[0.03] dark:hover:bg-white/[0.04] disabled:opacity-40"
                    onClick={() => {
                      setMoreOpen(false);
                      void handleBulkAutoSync(false);
                    }}
                  >
                    全部关闭自动跟进
                  </button>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => setScoutOpen((v) => !v)}
              className={cn(
                'ui-press h-9 px-3.5 rounded-lg text-[13px] font-medium inline-flex items-center gap-1.5',
                scoutOpen
                  ? 'bg-black/[0.06] dark:bg-white/[0.08] text-[var(--color-bone)]'
                  : 'bg-[var(--color-rust)] text-white hover:brightness-110 shadow-sm shadow-[var(--color-rust)]/20',
              )}
            >
              {scoutOpen ? (
                '收起'
              ) : (
                <>
                  <Plus className="w-3.5 h-3.5" strokeWidth={2.5} />
                  添加
                </>
              )}
            </button>
          </div>
        </div>
      </header>

      {scoutOpen && (
        <div className="border-b border-[var(--color-hairline)] bg-[var(--color-paper)]/40">
          <CreatorScout onCollected={() => setScoutOpen(false)} />
        </div>
      )}

      <section className="px-6 md:px-8 py-2.5 border-b border-[var(--color-hairline)] flex items-center gap-3 flex-wrap sticky top-[57px] z-[9] bg-[var(--color-ink)]/90 backdrop-blur-md">
        <div className="flex items-center gap-2 h-9 flex-1 min-w-[160px] max-w-xs rounded-lg bg-black/[0.03] dark:bg-white/[0.04] px-2.5 border border-transparent focus-within:border-[var(--color-rust)]/30 focus-within:bg-transparent transition-colors">
          <Search className="w-3.5 h-3.5 text-[var(--color-smoke)] shrink-0" strokeWidth={2} />
          <input
            type="text"
            placeholder="搜索…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 bg-transparent text-[13px] text-[var(--color-bone)] placeholder:text-[var(--color-smoke)] outline-none min-w-0"
          />
          {search && (
            <button type="button" onClick={() => setSearch('')} className="text-[var(--color-smoke)] hover:text-[var(--color-bone)] p-0.5">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center p-0.5 rounded-lg bg-black/[0.03] dark:bg-white/[0.04] gap-0.5 flex-wrap">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              data-active={filter === f.key}
              className={cn(
                'ui-seg ui-press h-8 px-2.5 text-[12px] font-medium rounded-md',
                filter === f.key
                  ? 'bg-[var(--color-paper)] text-[var(--color-bone)] shadow-sm'
                  : 'text-[var(--color-smoke)] hover:text-[var(--color-ash)]',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </section>

      {/* Bulk action bar — enter + exit */}
      <AnimatePresence initial={false}>
        {selectedCount > 0 && (
          <motion.div
            key="bulk-bar"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease: [0.2, 0.9, 0.3, 1] }}
            className="sticky top-[105px] z-[8] px-6 md:px-8 py-2 border-b border-[var(--color-rust)]/20 bg-[rgba(0,113,227,0.08)] backdrop-blur-md"
          >
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[13px] font-medium text-[var(--color-bone)] mr-1">
                已选 <span className="text-[var(--color-rust)] tabular-nums">{selectedCount}</span>
              </span>
              <button
                type="button"
                disabled={bulkBusy}
                onClick={() => openBulkRemove('keep_content')}
                className="ui-press h-8 px-2.5 rounded-lg text-[12px] font-medium inline-flex items-center gap-1.5 bg-[var(--color-paper)] text-[var(--color-bone)] border border-[var(--color-hairline)] hover:border-[var(--color-rust)]/40 disabled:opacity-40"
              >
                <Archive className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                停跟并保留
              </button>
              <button
                type="button"
                disabled={bulkBusy}
                onClick={() => openBulkRemove('purge')}
                className="ui-press h-8 px-2.5 rounded-lg text-[12px] font-medium inline-flex items-center gap-1.5 text-[var(--color-iron)] hover:bg-[rgba(239,68,68,0.08)] disabled:opacity-40"
              >
                <Trash2 className="w-3.5 h-3.5" />
                彻底删除
              </button>
              <span className="w-px h-4 bg-[var(--color-hairline-strong)] mx-0.5 hidden sm:block" />
              <button
                type="button"
                disabled={bulkBusy}
                onClick={() => void handleBulkSyncSelection()}
                className="ui-press h-8 px-2.5 rounded-lg text-[12px] font-medium inline-flex items-center gap-1.5 text-[var(--color-ash)] hover:bg-black/[0.04] dark:hover:bg-white/[0.05] disabled:opacity-40"
              >
                <RefreshCw
                  className={cn('w-3.5 h-3.5', bulkBusy && 'ui-sync-spin-loop text-[var(--color-rust)]')}
                />
                增量同步
              </button>
              <button
                type="button"
                disabled={bulkBusy}
                onClick={() => void handleBulkSetAutoOnSelection(true)}
                className="ui-press h-8 px-2.5 rounded-lg text-[12px] font-medium text-[var(--color-ash)] hover:bg-black/[0.04] dark:hover:bg-white/[0.05] disabled:opacity-40"
              >
                开自动
              </button>
              <button
                type="button"
                disabled={bulkBusy}
                onClick={() => void handleBulkSetAutoOnSelection(false)}
                className="ui-press h-8 px-2.5 rounded-lg text-[12px] font-medium text-[var(--color-ash)] hover:bg-black/[0.04] dark:hover:bg-white/[0.05] disabled:opacity-40"
              >
                关自动
              </button>
              <div className="flex-1" />
              <button
                type="button"
                onClick={clearSelection}
                className="ui-press h-8 px-2 rounded-lg text-[12px] text-[var(--color-smoke)] hover:text-[var(--color-bone)]"
              >
                取消选择
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="px-6 md:px-8 pb-12 pt-4">
        {hasLocalAssets && (
          <button
            type="button"
            onClick={() => navigate('/library/local:upload')}
            className="w-full mb-3 flex items-center justify-between px-3.5 py-2.5 rounded-xl border border-[var(--color-hairline)] hover:bg-black/[0.02] dark:hover:bg-white/[0.03] transition-colors group text-left"
          >
            <div className="min-w-0">
              <div className="text-[13px] font-medium text-[var(--color-bone)] group-hover:text-[var(--color-rust)]">
                本地素材
              </div>
              <div className="text-[11px] text-[var(--color-smoke)]">
                {localAssetCount} 条上传转写
              </div>
            </div>
            <ArrowRight className="w-4 h-4 text-[var(--color-smoke)] group-hover:text-[var(--color-rust)] shrink-0" />
          </button>
        )}

        <div className="rounded-xl border border-[var(--color-hairline)] overflow-hidden bg-[var(--color-paper)]/40">
          <CreatorListHeader
            allSelected={allFilteredSelected}
            someSelected={someFilteredSelected}
            onToggleAll={toggleSelectAllFiltered}
          />

          {loading ? (
            <div className="py-16 flex justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-[var(--color-smoke)]" />
            </div>
          ) : filteredCreators.length === 0 ? (
            <div className="py-16 text-center px-6">
              <div className="text-[14px] font-medium text-[var(--color-smoke)] mb-2">
                {search ? '无匹配' : '还没有创作者'}
              </div>
              {!search && (
                <button
                  type="button"
                  onClick={() => setScoutOpen(true)}
                  className="text-[13px] text-[var(--color-rust)] hover:underline"
                >
                  添加第一位
                </button>
              )}
            </div>
          ) : (
            filteredCreators.map((creator) => (
              <CreatorRow
                key={creator.uid}
                creator={creator}
                isSyncing={syncingIds.has(creator.uid)}
                isDeleting={deletingIds.has(creator.uid)}
                selected={selectedUids.has(creator.uid)}
                onToggleSelect={() => toggleSelectUid(creator.uid)}
                onOpen={() => navigate(`/library/${encodeURIComponent(creator.uid)}`)}
                onSync={(e) => handleSync(creator.uid, e)}
                onToggleAutoSync={() => handleToggleAutoSync(creator.uid)}
                onMore={(e) => {
                  e.stopPropagation();
                  setActionMenuCreator({ uid: creator.uid, nickname: creator.nickname || '' });
                }}
              />
            ))
          )}
        </div>

        {!loading && filteredCreators.length > 0 && (
          <p className="mt-3 text-[11px] text-[var(--color-smoke)] leading-relaxed">
            显示 {filteredCreators.length}/{creators.length}
            {' · '}
            勾选左侧方框可批量停跟 / 删除 / 同步
            {creators.length >= 500 ? ' · 列表上限 500' : ''}
          </p>
        )}
      </div>

      <LocalTranscribeModal
        isOpen={localTranscribeOpen}
        scannedFiles={scannedFiles}
        selectedFiles={selectedFiles}
        transcribing={transcribing}
        deleteAfter={deleteAfter}
        onClose={() => { setLocalTranscribeOpen(false); }}
        onSelectAll={() => setSelectedFiles(new Set(scannedFiles.map((f) => f.path)))}
        onClear={() => setSelectedFiles(new Set())}
        onToggleFile={toggleFileSelection}
        onToggleDeleteAfter={toggleDeleteAfter}
        onStart={handleStartLocalTranscribe}
      />

      <CreatorActionMenuModal
        creator={actionMenuCreator}
        creatorMeta={allCreators.find((c) => c.uid === actionMenuCreator?.uid) || null}
        onClose={() => setActionMenuCreator(null)}
        onSync={() => { handleSync(actionMenuCreator!.uid, { stopPropagation: () => { } }); setActionMenuCreator(null); }}
        onFullSync={() => { handleSync(actionMenuCreator!.uid, { stopPropagation: () => { } }, 'full'); setActionMenuCreator(null); }}
        isAutoSync={!!allCreators.find((c) => c.uid === actionMenuCreator?.uid)?.auto_sync}
        onToggleAutoSync={() => handleToggleAutoSync(actionMenuCreator!.uid)}
        onDelete={() => handleDeleteCreator(actionMenuCreator!.uid)}
        onRefollow={() => handleRefollow(actionMenuCreator!.uid)}
      />

      <DeleteConfirmModal
        targets={removeDialog?.targets ?? null}
        mode={removeDialog?.mode ?? 'keep_content'}
        onClose={() => setRemoveDialog(null)}
        deleting={bulkBusy || (!!removeDialog && removeDialog.targets.some((t) => deletingIds.has(t.uid)))}
        onModeChange={(mode) => setRemoveDialog((prev) => (prev ? { ...prev, mode } : null))}
        onConfirm={executeRemove}
      />
    </div>
  );
}
