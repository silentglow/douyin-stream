import {
  Search, Plus, Loader2, X, ArrowRight,
} from 'lucide-react';
import { useLibraryDetail } from '@/hooks/useLibraryDetail';
import { cn } from '@/lib/utils';
import { CreatorCard } from '@/components/library/CreatorCard';
import { CreatorActionMenuModal } from '@/components/library/CreatorActionMenuModal';
import { DeleteConfirmModal } from '@/components/library/DeleteConfirmModal';
import { LocalTranscribeModal } from '@/components/library/LocalTranscribeModal';

export default function Library() {
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
    newUrl,
    setNewUrl,
    isAdding,
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
    deleteConfirm,
    setDeleteConfirm,
    filteredCreators,
    handleAddCreator,
    handleSync,
    handleDeleteCreator,
    executeDeleteCreator,
    handleToggleAutoSync,
    handleSelectFolder,
    toggleFileSelection,
    handleStartLocalTranscribe,
    totalAssets,
    totalTranscribed,
    autoCount,
  } = useLibraryDetail();

  return (
    <div className="h-full overflow-y-auto page-enter">
      {/* ═══ MASTHEAD ═══════════════════════════════════════════ */}
      <header className="px-10 pt-12 pb-9 border-b border-[var(--color-hairline)]">
        <div className="flex items-end justify-between gap-10">
          <div>
            <div className="eyebrow mb-4">{creators.length} 位创作者在册</div>
            <h1 className="font-display text-[clamp(48px,6.5vw,96px)] leading-[0.95] tracking-display text-[var(--color-bone)]">
              内容库
            </h1>
            <p className="mt-4 text-[15px] leading-[1.55] text-[var(--color-ash)] max-w-xl">
              {totalAssets} 段影像在册 · <span className="text-[var(--color-bone)]">{totalTranscribed}</span> 段已转写 · <span className="text-[var(--color-rust)]">{autoCount}</span> 个自动同步
            </p>
          </div>

          <div className="flex items-center gap-2 pb-2">
            <button
              onClick={() => { const el = document.getElementById('add-creator-input'); el?.focus(); }}
              className="btn-sharp btn-primary"
            >
              + 添加创作者
            </button>
            <button
              onClick={handleSelectFolder}
              disabled={scanning}
              className="btn-sharp"
            >
              {scanning ? <Loader2 className="w-3.5 h-3.5 animate-spin inline mr-1" /> : null}
              本地上传
            </button>
          </div>
        </div>
      </header>

      {/* ═══ CONTROL STRIP ══════════════════════════════════════ */}
      <section className="px-10 py-5 border-b border-[var(--color-hairline)] flex items-center gap-8">
        {/* Search */}
        <div className="flex items-center gap-3 flex-1 max-w-md border-b border-[var(--color-hairline)] pb-2">
          <Search className="w-3.5 h-3.5 text-[var(--color-smoke)]" strokeWidth={1.5} />
          <input
            type="text"
            placeholder="搜索创作者..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 bg-transparent text-[15px] text-[var(--color-bone)] placeholder:text-[var(--color-smoke)] outline-none"
          />
          {search && (
            <button onClick={() => setSearch('')} className="text-[var(--color-smoke)] hover:text-[var(--color-rust)]">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Filter */}
        <div className="flex items-center gap-1">
          {(['all', 'video', 'transcript'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                'px-3 py-2 text-[12px] font-medium transition-colors border-b',
                filter === f
                  ? 'text-[var(--color-rust)] border-[var(--color-rust)]'
                  : 'text-[var(--color-smoke)] hover:text-[var(--color-bone)] border-transparent'
              )}
            >
              {f === 'all' ? '全部' : f === 'video' ? '有视频' : '有文稿'}
            </button>
          ))}
        </div>
      </section>

      {/* ═══ ADD CREATOR INPUT ══════════════════════════════════ */}
      <section className="px-10 py-5 border-b border-[var(--color-hairline)]">
        <div className="flex items-center gap-4">
          <input
            id="add-creator-input"
            type="text"
            placeholder="粘贴创作者主页链接 → 收录"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddCreator()}
            className="flex-1 bg-transparent border-b border-[var(--color-hairline)] py-2 text-[15px] text-[var(--color-bone)] placeholder:text-[var(--color-smoke)] outline-none focus:border-[var(--color-rust)] transition-colors"
          />
          <button
            onClick={handleAddCreator}
            disabled={!newUrl.trim() || isAdding}
            className="btn-sharp btn-primary disabled:opacity-40 flex items-center gap-2"
          >
            {isAdding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            收录
          </button>
        </div>
      </section>

      <div className="px-10 pb-12 pt-8">
        <LocalTranscribeModal
          isOpen={localTranscribeOpen}
          scannedFiles={scannedFiles}
          selectedFiles={selectedFiles}
          transcribing={transcribing}
          onClose={() => { setLocalTranscribeOpen(false); }}
          onSelectAll={() => setSelectedFiles(new Set(scannedFiles.map((f) => f.path)))}
          onClear={() => setSelectedFiles(new Set())}
          onToggleFile={toggleFileSelection}
          onStart={handleStartLocalTranscribe}
        />

        {/* Roster section header */}
        <div className="flex items-baseline justify-between mb-6 pb-3 border-b border-[var(--color-hairline-strong)]">
          <h2 className="font-display text-[28px] text-[var(--color-bone)] leading-none">
            名册
            <span className="ml-3 text-[14px] text-[var(--color-smoke)] font-sans">
              {filteredCreators.length} / {creators.length}
            </span>
          </h2>
          {hasLocalAssets && (
            <button
              onClick={() => navigate('/library/local:upload')}
              className="flex items-center gap-2 group"
            >
              <span className="text-[12px] text-[var(--color-ash)] group-hover:text-[var(--color-rust)] transition-colors">
                本地素材 · {localAssetCount}
              </span>
              <ArrowRight className="w-3.5 h-3.5 text-[var(--color-ash)] group-hover:text-[var(--color-rust)] transition-colors" />
            </button>
          )}
        </div>

        {/* Roster grid */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="ed-card h-[160px] skeleton" />
            ))}
          </div>
        ) : filteredCreators.length === 0 ? (
          <div className="py-20 text-center">
            <div className="font-display text-[32px] text-[var(--color-smoke)] mb-3">
              {search ? '无匹配' : '名册为空'}
            </div>
            {!search && (
              <div className="text-[13px] text-[var(--color-ash)]">
                在上方粘贴主页链接以收录
              </div>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5 stagger">
            {filteredCreators.map((creator) => (
              <CreatorCard
                key={creator.uid}
                creator={creator}
                isSyncing={syncingIds.has(creator.uid)}
                isDeleting={deletingIds.has(creator.uid)}
                onClick={() => navigate(`/library/${encodeURIComponent(creator.uid)}`)}
                onSync={(e) => handleSync(creator.uid, e)}
                onMore={(e) => { e.stopPropagation(); setActionMenuCreator({ uid: creator.uid, nickname: creator.nickname || '' }); }}
              />
            ))}
          </div>
        )}
      </div>

      <CreatorActionMenuModal
        creator={actionMenuCreator}
        onClose={() => setActionMenuCreator(null)}
        onSync={() => { handleSync(actionMenuCreator!.uid, { stopPropagation: () => { } }); setActionMenuCreator(null); }}
        onFullSync={() => { handleSync(actionMenuCreator!.uid, { stopPropagation: () => { } }, 'full'); setActionMenuCreator(null); }}
        isAutoSync={!!allCreators.find((c) => c.uid === actionMenuCreator?.uid)?.auto_sync}
        onToggleAutoSync={() => handleToggleAutoSync(actionMenuCreator!.uid)}
        onDelete={() => handleDeleteCreator(actionMenuCreator!.uid)}
      />

      <DeleteConfirmModal
        deleteConfirm={deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        deleting={deletingIds.has(deleteConfirm?.uid || '')}
        onCheckboxChange={(checked) => setDeleteConfirm((prev) => prev ? { ...prev, deleteAssets: checked } : null)}
        onConfirm={executeDeleteCreator}
      />
    </div>
  );
}
