import { useMemo, useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, Plus, Loader2, RefreshCw, X, ArrowRight,
  Trash2, MoreHorizontal,
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useStore } from '@/store/useStore';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  addCreator, deleteCreator, triggerCreatorDownload, toggleCreatorAutoSync, getAssetsByCreator, bulkDeleteAssets,
} from '@/lib/api';
import { selectFolder, scanDirectory, triggerLocalTranscribe } from '@/lib/api';

type FilterType = 'all' | 'video' | 'transcript';

export default function Library() {
  const navigate = useNavigate();
  const allCreators = useStore((state) => state.creators);
  const storeFetchCreators = useStore((state) => state.fetchCreators);

  const creators = useMemo(
    () => allCreators.filter((c) => c.platform !== 'local' && !c.uid.startsWith('local:')),
    [allCreators]
  );

  const hasLocalAssets = allCreators.some((c) => c.uid === 'local:upload');
  const localAssetCount = allCreators.find((c) => c.uid === 'local:upload')?.asset_count || 0;

  const [filter, setFilter] = useState<FilterType>('all');
  const [search, setSearch] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [actionMenuCreator, setActionMenuCreator] = useState<{ uid: string; nickname: string } | null>(null);

  const [localTranscribeOpen, setLocalTranscribeOpen] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scannedFiles, setScannedFiles] = useState<Array<{ path: string; name: string }>>([]);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [transcribing, setTranscribing] = useState(false);
  const [scannedDirectory, setScannedDirectory] = useState('');

  const [deleteConfirm, setDeleteConfirm] = useState<{
    uid: string;
    nickname: string;
    assetCount: number;
    deleteAssets: boolean;
  } | null>(null);

  useEffect(() => { storeFetchCreators().then(() => setLoading(false)); }, [storeFetchCreators]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (actionMenuCreator) setActionMenuCreator(null);
        else if (localTranscribeOpen) {
          setLocalTranscribeOpen(false);
          setScannedFiles([]);
          setSelectedFiles(new Set());
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [actionMenuCreator, localTranscribeOpen]);

  const filteredCreators = useMemo(() => {
    let result = creators;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter((c) =>
        c.nickname?.toLowerCase().includes(q) || c.uid?.toLowerCase().includes(q)
      );
    }
    if (filter === 'video') result = result.filter((c) => (c.asset_count || 0) > 0);
    else if (filter === 'transcript') result = result.filter((c) => (c.transcript_completed_count || 0) > 0);
    return result;
  }, [creators, search, filter]);

  const handleAddCreator = useCallback(async () => {
    if (!newUrl.trim()) return;
    setIsAdding(true);
    try {
      await addCreator(newUrl.trim());
      toast.success('创作者已收录');
      setNewUrl('');
      await storeFetchCreators(true);
    } catch { /* api interceptor handles toast */ }
    finally { setIsAdding(false); }
  }, [newUrl, storeFetchCreators]);

  const handleSync = useCallback(async (uid: string, e: React.MouseEvent, mode: 'incremental' | 'full' = 'incremental') => {
    e.stopPropagation();
    if (syncingIds.has(uid)) return;
    if (mode === 'full' && !window.confirm('全量重拉将重新下载该创作者的所有视频（包括本地已有的），可能消耗大量网络和磁盘。确定继续？')) {
      return;
    }
    setSyncingIds((prev) => new Set(prev).add(uid));
    try {
      await triggerCreatorDownload(uid, mode);
      toast.success(mode === 'full' ? '全量同步任务已派发' : '同步任务已派发');
    } catch { /* api interceptor handles toast */ }
    finally {
      setSyncingIds((prev) => { const next = new Set(prev); next.delete(uid); return next; });
    }
  }, [syncingIds]);

  const handleDeleteCreator = useCallback((uid: string) => {
    const creator = allCreators.find((c) => c.uid === uid);
    if (!creator) return;
    setDeleteConfirm({ uid, nickname: creator.nickname || '创作者', assetCount: creator.asset_count || 0, deleteAssets: false });
    setActionMenuCreator(null);
  }, [allCreators]);

  const executeDeleteCreator = useCallback(async () => {
    if (!deleteConfirm) return;
    const { uid, deleteAssets, assetCount } = deleteConfirm;
    setDeletingIds((prev) => new Set(prev).add(uid));
    try {
      if (deleteAssets && assetCount > 0) {
        const assets = await getAssetsByCreator(uid);
        if (assets.length > 0) await bulkDeleteAssets(assets.map((a) => a.asset_id));
      }
      await deleteCreator(uid);
      toast.success(deleteAssets ? '已删除创作者及素材' : '已删除创作者');
      await storeFetchCreators(true);
    } catch {
      toast.error('删除失败');
    } finally {
      setDeletingIds((prev) => { const next = new Set(prev); next.delete(uid); return next; });
      setDeleteConfirm(null);
    }
  }, [deleteConfirm, storeFetchCreators]);

  const handleToggleAutoSync = useCallback(async (uid: string) => {
    const creator = creators.find((c) => c.uid === uid);
    if (!creator) return;
    const newValue = !creator.auto_sync;
    try {
      await toggleCreatorAutoSync(uid, !!newValue);
      useStore.setState((state) => ({
        creators: state.creators.map((c) => c.uid === uid ? { ...c, auto_sync: !!newValue } : c),
      }));
      toast.success(!!newValue ? '已开启自动同步' : '已关闭自动同步');
    } catch { /* api interceptor handles toast */ }
  }, [creators]);

  const handleSelectFolder = useCallback(async () => {
    setScanning(true);
    try {
      const { directory } = await selectFolder();
      const { files } = await scanDirectory(directory);
      setScannedDirectory(directory);
      setScannedFiles(files.map((f: any) => ({ path: f.path, name: f.name })));
      setSelectedFiles(new Set(files.map((f: any) => f.path)));
      setLocalTranscribeOpen(true);
    } catch { /* api interceptor handles toast */ }
    finally { setScanning(false); }
  }, []);

  const toggleFileSelection = useCallback((path: string) => {
    setSelectedFiles((prev) => { const next = new Set(prev); if (next.has(path)) next.delete(path); else next.add(path); return next; });
  }, []);

  const handleStartLocalTranscribe = useCallback(async () => {
    if (selectedFiles.size === 0) return;
    setTranscribing(true);
    try {
      const paths = Array.from(selectedFiles);
      await triggerLocalTranscribe(paths, false, scannedDirectory);
      toast.success(`已提交 ${paths.length} 个文件的转写任务`);
      setLocalTranscribeOpen(false);
      setScannedFiles([]);
      setSelectedFiles(new Set());
      setScannedDirectory('');
    } catch { /* api interceptor handles toast */ }
    finally { setTranscribing(false); }
  }, [selectedFiles, scannedDirectory]);

  const totalAssets = creators.reduce((s, c) => s + (c.asset_count || 0), 0);
  const totalTranscribed = creators.reduce((s, c) => s + (c.transcript_completed_count || 0), 0);
  const autoCount = creators.filter(c => c.auto_sync).length;

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
        {/* Scanned files panel */}
        <AnimatePresence>
          {localTranscribeOpen && scannedFiles.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="ed-card p-6 mb-8"
            >
              <div className="flex items-baseline justify-between mb-4 pb-3 border-b border-[var(--color-hairline)]">
                <div>
                  <div className="eyebrow mb-1">已扫描目录</div>
                  <div className="font-display text-[22px] text-[var(--color-bone)]">
                    发现 {scannedFiles.length} 个文件
                  </div>
                </div>
                <button onClick={() => { setLocalTranscribeOpen(false); setScannedFiles([]); setSelectedFiles(new Set()); }} className="text-[var(--color-smoke)] hover:text-[var(--color-rust)]">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex items-center gap-4 mb-3">
                <button onClick={() => setSelectedFiles(new Set(scannedFiles.map((f) => f.path)))} className="draw-line text-[12px] text-[var(--color-rust)]">全选</button>
                <button onClick={() => setSelectedFiles(new Set())} className="draw-line text-[12px] text-[var(--color-ash)]">清除</button>
              </div>
              <div className="max-h-[240px] overflow-y-auto -mx-2">
                {scannedFiles.map((file) => (
                  <label key={file.path} className="flex items-center gap-3 px-2 py-2 hover:bg-[rgba(243,238,219,0.02)] cursor-pointer transition-colors">
                    <input type="checkbox" checked={selectedFiles.has(file.path)} onChange={() => toggleFileSelection(file.path)} className="w-3.5 h-3.5 accent-[var(--color-rust)]" />
                    <span className="text-[13px] text-[var(--color-bone)] truncate flex-1 font-mono">{file.name}</span>
                  </label>
                ))}
              </div>
              <div className="flex items-center justify-between mt-5 pt-4 border-t border-[var(--color-hairline)]">
                <span className="text-[12px] text-[var(--color-ash)]">
                  <span className="font-display text-[20px] text-[var(--color-rust)] tabular mr-1">{selectedFiles.size}</span>
                  / {scannedFiles.length} 已选
                </span>
                <div className="flex gap-2">
                  <button onClick={() => { setLocalTranscribeOpen(false); setScannedFiles([]); setSelectedFiles(new Set()); }} className="btn-sharp">取消</button>
                  <button onClick={handleStartLocalTranscribe} disabled={selectedFiles.size === 0 || transcribing} className="btn-sharp btn-primary disabled:opacity-40 flex items-center gap-2">
                    {transcribing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                    开始转写
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

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
          <div className="grid grid-cols-3 lg:grid-cols-4 gap-px bg-[var(--color-hairline-faint)]">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="bg-[var(--color-ink)] p-5 h-[160px] skeleton" />
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
          <div className="grid grid-cols-3 lg:grid-cols-4 gap-px bg-[var(--color-hairline-faint)] stagger">
            {filteredCreators.map((creator) => {
              const isSyncing = syncingIds.has(creator.uid);
              const isDeleting = deletingIds.has(creator.uid);
              return (
                <motion.div
                  key={creator.uid}
                  layout
                  className="bg-[var(--color-ink)] p-5 cursor-pointer group hover:bg-[var(--color-paper)] transition-colors relative"
                  onClick={() => navigate(`/library/${encodeURIComponent(creator.uid)}`)}
                >
                  {/* Auto/manual badge */}
                  <div className="flex justify-end mb-3">
                    <span className={cn('text-[10px] tracking-[0.16em] uppercase', creator.auto_sync ? 'text-[var(--color-rust)]' : 'text-[var(--color-smoke)]')}>
                      {creator.auto_sync ? '自动' : '手动'}
                    </span>
                  </div>

                  {/* Name */}
                  <div className="font-display text-[24px] text-[var(--color-bone)] leading-tight group-hover:text-[var(--color-rust)] transition-colors line-clamp-2 min-h-[60px]">
                    {creator.nickname || '未命名'}
                  </div>

                  {/* Stats */}
                  <div className="mt-4 pt-3 border-t border-[var(--color-hairline-faint)] flex items-baseline justify-between">
                    <span className="text-[12px] text-[var(--color-ash)]">
                      <span className="font-display text-[18px] text-[var(--color-bone)] tabular mr-1">{creator.asset_count || 0}</span>
                      视频
                    </span>
                    <span className="text-[12px] text-[var(--color-ash)]">
                      <span className="font-display text-[18px] text-[var(--color-rust)] tabular mr-1">{creator.transcript_completed_count || 0}</span>
                      文稿
                    </span>
                  </div>

                  {/* Hover actions */}
                  <div className="absolute top-3 left-3 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => handleSync(creator.uid, e)}
                      disabled={isSyncing || isDeleting}
                      className="w-7 h-7 flex items-center justify-center bg-[var(--color-vellum)] border border-[var(--color-hairline-strong)] hover:border-[var(--color-rust)] hover:text-[var(--color-rust)] transition-colors text-[var(--color-ash)]"
                      title="同步"
                    >
                      {isSyncing ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setActionMenuCreator({ uid: creator.uid, nickname: creator.nickname }); }}
                      disabled={isDeleting}
                      className="w-7 h-7 flex items-center justify-center bg-[var(--color-vellum)] border border-[var(--color-hairline-strong)] hover:border-[var(--color-rust)] hover:text-[var(--color-rust)] transition-colors text-[var(--color-ash)]"
                      title="更多"
                    >
                      {isDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <MoreHorizontal className="w-3 h-3" />}
                    </button>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* Action Menu Modal */}
      <AnimatePresence>
        {actionMenuCreator && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setActionMenuCreator(null)}
          >
            <motion.div
              initial={{ y: '100%', opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: '100%', opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="bg-[var(--color-paper)] w-full sm:max-w-sm sm:mx-4 border border-[var(--color-hairline-strong)] overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-5 border-b border-[var(--color-hairline)]">
                <div className="eyebrow mb-1">creator dossier</div>
                <div className="font-display text-[22px] text-[var(--color-bone)] truncate">{actionMenuCreator.nickname}</div>
              </div>
              <div>
                <button
                  onClick={() => { handleSync(actionMenuCreator.uid, { stopPropagation: () => { } } as React.MouseEvent); setActionMenuCreator(null); }}
                  className="w-full flex items-center gap-4 px-5 py-4 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group"
                >
                  <RefreshCw className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                  <span className="font-display text-[18px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">立即同步</span>
                </button>
                <button
                  onClick={() => { handleSync(actionMenuCreator.uid, { stopPropagation: () => { } } as React.MouseEvent, 'full'); setActionMenuCreator(null); }}
                  className="w-full flex items-center gap-4 px-5 py-4 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group"
                >
                  <RefreshCw className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                  <span className="font-display text-[18px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">全量重拉</span>
                </button>
                <div className="w-full flex items-center justify-between px-5 py-4 border-b border-[var(--color-hairline-faint)]">
                  <span className="font-display text-[18px] text-[var(--color-bone)]">自动同步</span>
                  <Switch
                    checked={!!allCreators.find((c) => c.uid === actionMenuCreator.uid)?.auto_sync}
                    onCheckedChange={() => handleToggleAutoSync(actionMenuCreator.uid)}
                  />
                </div>
                <button
                  onClick={() => handleDeleteCreator(actionMenuCreator.uid)}
                  className="w-full flex items-center gap-4 px-5 py-4 hover:bg-[rgba(178,89,80,0.08)] transition-colors text-left group"
                >
                  <Trash2 className="w-3.5 h-3.5 text-[var(--color-iron)]" />
                  <span className="font-display text-[18px] text-[var(--color-iron)]">删除创作者</span>
                </button>
              </div>
              <div className="p-3 border-t border-[var(--color-hairline)]">
                <button onClick={() => setActionMenuCreator(null)} className="w-full btn-sharp">cancel · 取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Delete Confirm */}
      <AnimatePresence>
        {deleteConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-md px-4"
            onClick={() => setDeleteConfirm(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-[var(--color-paper)] p-7 w-full max-w-md border border-[var(--color-iron)]/30"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="eyebrow text-[var(--color-iron)] mb-2">errata · destructive</div>
              <h3 className="font-display text-[36px] text-[var(--color-bone)] leading-tight">
                Remove from roster?
              </h3>
              <p className="font-display text-[18px] text-[var(--color-ash)] mt-2">
                <span className="text-[var(--color-bone)]">{deleteConfirm.nickname}</span> will no longer be subscribed.
              </p>

              {deleteConfirm.assetCount > 0 && (
                <div className="mt-5 pt-5 border-t border-[var(--color-hairline)]">
                  <p className="text-[13px] text-[var(--color-ash)]">
                    associated:{' '}
                    <span className="font-display text-[22px] text-[var(--color-bone)] tabular">{deleteConfirm.assetCount}</span>{' '}
                    archived films
                  </p>
                  <label className="mt-3 flex items-center gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={deleteConfirm.deleteAssets}
                      onChange={(e) => setDeleteConfirm({ ...deleteConfirm, deleteAssets: e.target.checked })}
                      className="w-4 h-4 accent-[var(--color-iron)]"
                    />
                    <span className="text-[13px] text-[var(--color-bone)]">连同素材一并删除（不可恢复）</span>
                  </label>
                </div>
              )}

              <div className="flex gap-2 mt-7">
                <button onClick={() => setDeleteConfirm(null)} className="flex-1 btn-sharp">取消</button>
                <button
                  onClick={executeDeleteCreator}
                  disabled={deletingIds.has(deleteConfirm.uid)}
                  className="flex-1 btn-sharp border-[var(--color-iron)] text-[var(--color-iron)] hover:bg-[var(--color-iron)] hover:text-[var(--color-ink)] disabled:opacity-40 flex items-center justify-center gap-2"
                >
                  {deletingIds.has(deleteConfirm.uid)
                    ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> 删除中</>
                    : (deleteConfirm.deleteAssets ? '删除全部' : '仅删除创作者')}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
