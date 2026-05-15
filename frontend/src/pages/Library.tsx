import { useMemo, useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, Users, Plus, Loader2, RefreshCw, FileAudio, X, ArrowRight,
  Trash2, MoreHorizontal, FileText, Star
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useStore } from '@/store/useStore';
import { AppleEmptyState } from '@/components/ui/AppleEmptyState';
import { Switch } from '@/components/ui/switch';
import { TranscriptReader } from '@/components/ui/TranscriptReader';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { addCreator, deleteCreator, triggerCreatorDownload, toggleCreatorAutoSync, getAssetsByCreator, bulkDeleteAssets } from '@/lib/api';
import { selectFolder, scanDirectory, triggerLocalTranscribe, getRecentTranscripts, getAssetTranscript } from '@/lib/api';
import type { Asset } from '@/types';

const gradients = [
  'from-[#5E9CEA] to-[#7B8CDE]',
  'from-[#E88B8B] to-[#D97B9E]',
  'from-[#6BC4A6] to-[#5DB8C8]',
  'from-[#E8A96E] to-[#E8C46E]',
  'from-[#B8A0D9] to-[#9BA5D9]',
  'from-[#8BC4E0] to-[#7BB0D9]',
  'from-[#E0A0A0] to-[#D9B0B0]',
  'from-[#A0D9C0] to-[#90C8B0]',
];

function getGradient(index: number) {
  return gradients[index % gradients.length];
}

type FilterType = 'all' | 'video' | 'transcript';

export default function Library() {
  const navigate = useNavigate();
  const settings = useStore((state) => state.settings);
  const allCreators = useStore((state) => state.creators);
  const storeFetchCreators = useStore((state) => state.fetchCreators);

  const creators = useMemo(
    () => allCreators.filter((c) => c.platform !== 'local' && !c.uid.startsWith('local:')),
    [allCreators]
  );

  // 本地素材虚拟创作者
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

  // Local transcribe state
  const [localTranscribeOpen, setLocalTranscribeOpen] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scannedFiles, setScannedFiles] = useState<Array<{ path: string; name: string }>>([]);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [transcribing, setTranscribing] = useState(false);
  const [scannedDirectory, setScannedDirectory] = useState('');

  // Recent transcripts state
  const [recentTranscripts, setRecentTranscripts] = useState<Asset[]>([]);

  // Transcript reader state
  const [readingAsset, setReadingAsset] = useState<Asset | null>(null);
  const [readingContent, setReadingContent] = useState('');
  const [readingLoading, setReadingLoading] = useState(false);

  // Delete confirmation state
  const [deleteConfirm, setDeleteConfirm] = useState<{
    uid: string;
    nickname: string;
    assetCount: number;
    deleteAssets: boolean;
  } | null>(null);

  useEffect(() => {
    storeFetchCreators().then(() => setLoading(false));
  }, [storeFetchCreators]);

  // Load recent transcripts
  useEffect(() => {
    let cancelled = false;
    getRecentTranscripts(10)
      .then((data) => { if (!cancelled) setRecentTranscripts(data); })
      .catch(() => { /* ignore */ });
    return () => { cancelled = true; };
  }, []);

  const handleOpenTranscript = useCallback(async (asset: Asset) => {
    setReadingAsset(asset);
    setReadingLoading(true);
    setReadingContent('');
    try {
      const content = await getAssetTranscript(asset.asset_id);
      setReadingContent(content);
    } catch {
      toast.error('获取转写内容失败');
    } finally {
      setReadingLoading(false);
    }
  }, []);

  /* Global keyboard shortcuts */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (readingAsset) {
          e.preventDefault();
          setReadingAsset(null);
          setReadingContent('');
        } else if (actionMenuCreator) {
          e.preventDefault();
          setActionMenuCreator(null);
        } else if (localTranscribeOpen) {
          e.preventDefault();
          setLocalTranscribeOpen(false);
          setScannedFiles([]);
          setSelectedFiles(new Set());
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [readingAsset, actionMenuCreator, localTranscribeOpen]);

  const filteredCreators = useMemo(() => {
    let result = creators;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter((c) =>
        c.nickname?.toLowerCase().includes(q) ||
        c.uid?.toLowerCase().includes(q)
      );
    }
    if (filter === 'video') {
      result = result.filter((c) => (c.asset_count || 0) > 0);
    } else if (filter === 'transcript') {
      result = result.filter((c) =>
        (c.transcript_completed_count || 0) > 0
      );
    }
    return result;
  }, [creators, search, filter]);

  const handleAddCreator = useCallback(async () => {
    if (!newUrl.trim()) return;
    setIsAdding(true);
    try {
      await addCreator(newUrl.trim());
      toast.success('创作者添加成功');
      setNewUrl('');
      await storeFetchCreators(true);
    } catch {
      // api interceptor handles toast
    } finally {
      setIsAdding(false);
    }
  }, [newUrl, storeFetchCreators]);

  const handleSync = useCallback(async (uid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (syncingIds.has(uid)) return;
    setSyncingIds((prev) => new Set(prev).add(uid));
    try {
      await triggerCreatorDownload(uid, 'incremental');
      toast.success('同步任务已启动');
    } catch {
      // api interceptor handles toast
    } finally {
      setSyncingIds((prev) => {
        const next = new Set(prev);
        next.delete(uid);
        return next;
      });
    }
  }, [syncingIds]);

  const handleDeleteCreator = useCallback((uid: string) => {
    const creator = allCreators.find((c) => c.uid === uid);
    if (!creator) return;
    setDeleteConfirm({
      uid,
      nickname: creator.nickname || '创作者',
      assetCount: creator.asset_count || 0,
      deleteAssets: false,
    });
    setActionMenuCreator(null);
  }, [allCreators]);

  const executeDeleteCreator = useCallback(async () => {
    if (!deleteConfirm) return;
    const { uid, deleteAssets, assetCount } = deleteConfirm;
    setDeletingIds((prev) => new Set(prev).add(uid));
    try {
      if (deleteAssets && assetCount > 0) {
        const assets = await getAssetsByCreator(uid);
        if (assets.length > 0) {
          await bulkDeleteAssets(assets.map((a) => a.asset_id));
        }
      }
      await deleteCreator(uid);
      toast.success(deleteAssets ? '创作者及素材已删除' : '创作者已删除');
      await storeFetchCreators(true);
    } catch {
      toast.error('删除失败');
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(uid);
        return next;
      });
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
        creators: state.creators.map((c) =>
          c.uid === uid ? { ...c, auto_sync: !!newValue } : c
        ),
      }));
      toast.success(!!newValue ? '已开启自动同步' : '已关闭自动同步');
    } catch {
      // api interceptor handles toast
    }
  }, [creators]);

  // Local transcribe handlers
  const handleSelectFolder = useCallback(async () => {
    setScanning(true);
    try {
      const { directory } = await selectFolder();
      const { files } = await scanDirectory(directory);
      setScannedDirectory(directory);
      setScannedFiles(files.map((f) => ({ path: f.path, name: f.name })));
      setSelectedFiles(new Set(files.map((f) => f.path)));
      setLocalTranscribeOpen(true);
    } catch {
      // api interceptor handles toast
    } finally {
      setScanning(false);
    }
  }, []);

  const toggleFileSelection = useCallback((path: string) => {
    setSelectedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
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
    } catch {
      // api interceptor handles toast
    } finally {
      setTranscribing(false);
    }
  }, [selectedFiles, scannedDirectory]);

  const douyinReady = settings?.status_summary.douyin_ready ?? false;
  const bilibiliReady = (settings?.status_summary.bilibili_accounts_count ?? 0) > 0;
  const canDownloadAny = settings?.status_summary.can_download ?? false;

  return (
    <div className="h-full p-7 px-8 max-sm:p-4 max-sm:pb-20 overflow-y-auto">
      <div className="text-title-1 font-bold mb-6 tracking-tight">内容库</div>

      {/* Recent Transcripts */}
      {!loading && recentTranscripts.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="mb-6"
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <FileText className="size-4 text-primary" />
              <span className="text-sm font-semibold">最近转写</span>
            </div>
            <button
              onClick={() => setFilter('transcript')}
              className="text-xs text-primary hover:underline"
            >
              查看全部
            </button>
          </div>
          <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1 scrollbar-hide">
            {recentTranscripts.map((asset, i) => (
              <motion.div
                key={asset.asset_id}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.05 }}
                whileHover={{ scale: 0.98 }}
                whileTap={{ scale: 0.96 }}
                onClick={() => handleOpenTranscript(asset)}
                className="shrink-0 w-[200px] bg-card rounded-[18px] apple-shadow-widget p-3.5 cursor-pointer transition-shadow"
              >
                <div className="flex items-center gap-2 mb-2">
                  <div className={cn(
                    'w-7 h-7 rounded-lg flex items-center justify-center',
                    asset.transcript_status === 'COMPLETED' ? 'bg-success/10' : 'bg-secondary'
                  )}>
                    <FileText className="size-3.5 text-success" />
                  </div>
                  <span className="text-[11px] text-muted-foreground truncate">
                    {allCreators.find((c) => c.uid === asset.creator_uid)?.nickname || '本地素材'}
                  </span>
                </div>
                <div className="text-sm font-medium truncate mb-1">{asset.title || '未命名'}</div>
                <div className="text-[11px] text-muted-foreground line-clamp-2">
                  {asset.transcript_preview || '暂无预览'}
                </div>
                {asset.is_starred && (
                  <div className="mt-2 inline-flex items-center gap-1 text-[10px] text-warning">
                    <Star className="size-2.5 fill-warning" /> 已收藏
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Segmented Control */}
      <div className="inline-flex bg-secondary rounded-lg p-[3px] mb-5">
        {([
          { key: 'all', label: '全部' },
          { key: 'video', label: '视频' },
          { key: 'transcript', label: '转写文本' },
        ] as const).map((item) => (
          <button
            key={item.key}
            onClick={() => setFilter(item.key)}
            className={cn(
              'px-5 py-[7px] rounded-md text-sm font-medium transition-all duration-200',
              filter === item.key
                ? 'bg-card text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Search Bar */}
      <div className="flex items-center gap-3 bg-secondary rounded-xl px-4 py-2.5 mb-5">
        <Search className="size-4 text-muted-foreground shrink-0" />
        <input
          type="text"
          placeholder="搜索创作者或视频..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 bg-transparent text-body outline-none placeholder:text-muted-foreground"
        />
      </div>

      {/* Add Creator */}
      <div className="flex gap-2 mb-6">
        <input
          type="text"
          placeholder="粘贴创作者主页链接..."
          value={newUrl}
          onChange={(e) => setNewUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAddCreator()}
          disabled={!canDownloadAny || isAdding}
          className="flex-1 bg-card border border-border/40 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-primary/50 transition-colors disabled:opacity-50"
        />
        <button
          onClick={handleAddCreator}
          disabled={!canDownloadAny || !newUrl.trim() || isAdding}
          className="flex items-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary/90 transition-all active:scale-[0.96] disabled:opacity-50"
        >
          {isAdding ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
          添加
        </button>
      </div>

      {/* Local Transcribe */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={handleSelectFolder}
          disabled={scanning}
          className="flex items-center gap-2 px-4 py-2.5 bg-secondary text-foreground rounded-xl text-sm font-medium hover:bg-secondary/80 transition-all active:scale-[0.97] disabled:opacity-50"
        >
          {scanning ? <Loader2 className="size-4 animate-spin" /> : <FileAudio className="size-4" />}
          本地转写
        </button>
      </div>

      {/* Scanned Files Panel */}
      {localTranscribeOpen && scannedFiles.length > 0 && (
        <div className="bg-card rounded-[22px] apple-shadow-widget p-5 mb-6">
          <div className="flex items-center justify-between mb-3">
            <div className="text-body font-semibold">扫描到 {scannedFiles.length} 个文件</div>
            <button
              onClick={() => {
                setLocalTranscribeOpen(false);
                setScannedFiles([]);
                setSelectedFiles(new Set());
              }}
              className="p-1.5 rounded-lg hover:bg-secondary transition-colors"
            >
              <X className="size-4 text-muted-foreground" />
            </button>
          </div>
          <div className="flex items-center gap-2 mb-2">
            <button
              onClick={() => setSelectedFiles(new Set(scannedFiles.map((f) => f.path)))}
              className="text-xs text-primary font-medium hover:underline"
            >
              全选
            </button>
            <button
              onClick={() => setSelectedFiles(new Set())}
              className="text-xs text-muted-foreground hover:underline"
            >
              取消全选
            </button>
          </div>
          <div className="max-h-[240px] overflow-y-auto space-y-1 mb-4">
            {scannedFiles.map((file) => (
              <label
                key={file.path}
                className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-secondary/50 cursor-pointer transition-colors"
              >
                <input
                  type="checkbox"
                  checked={selectedFiles.has(file.path)}
                  onChange={() => toggleFileSelection(file.path)}
                  className="size-4 rounded border-border accent-primary"
                />
                <span className="text-sm truncate flex-1">{file.name}</span>
                {'size_mb' in file && file.size_mb !== undefined && (
                  <span className="text-xs text-muted-foreground shrink-0">{(file as unknown as { size_mb: number }).size_mb.toFixed(1)} MB</span>
                )}
              </label>
            ))}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-caption text-muted-foreground">已选择 {selectedFiles.size} 个</span>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setLocalTranscribeOpen(false);
                  setScannedFiles([]);
                  setSelectedFiles(new Set());
                }}
                className="px-4 py-2 rounded-xl bg-secondary text-sm font-medium hover:bg-secondary/80 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleStartLocalTranscribe}
                disabled={selectedFiles.size === 0 || transcribing}
                className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-all active:scale-[0.96] disabled:opacity-50"
              >
                {transcribing ? <Loader2 className="size-4 animate-spin" /> : '开始转写'}
              </button>
            </div>
          </div>
        </div>
      )}

      {!douyinReady && !bilibiliReady && (
        <div className="text-xs text-muted-foreground mb-4">
          先在设置页配置抖音或 B站 Cookie 才能添加创作者
        </div>
      )}

      {/* Local Assets Entry */}
      {hasLocalAssets && (
        <div className="mb-5">
          <div
            className="bg-card rounded-[22px] apple-shadow-widget overflow-hidden cursor-pointer transition-all duration-200 active:scale-[0.97] flex items-center gap-4 px-5 py-4"
            onClick={() => navigate('/library/local:upload')}
          >
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#6BC4A6] to-[#5DB8A0] flex items-center justify-center shrink-0">
              <FileAudio className="size-6 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-body truncate">本地素材</div>
              <div className="text-caption text-muted-foreground">
                {localAssetCount} 个文件
              </div>
            </div>
            <ArrowRight className="size-4 text-muted-foreground shrink-0" />
          </div>
        </div>
      )}

      {/* Creator Grid */}
      {loading ? (
        <div className="grid grid-cols-4 max-lg:grid-cols-3 max-sm:grid-cols-2 gap-5">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-card rounded-[22px] aspect-square apple-skeleton" />
          ))}
        </div>
      ) : filteredCreators.length === 0 ? (
        <AppleEmptyState
          icon={<Users className="size-8 stroke-[1.5]" />}
          title="还没有创作者"
          description={search ? '没有匹配的创作者' : '在上方输入框粘贴主页链接添加创作者'}
        />
      ) : (
        <div className="grid grid-cols-4 max-lg:grid-cols-3 max-sm:grid-cols-2 gap-5">
          {filteredCreators.map((creator, i) => {
            const isSyncing = syncingIds.has(creator.uid);
            const isDeleting = deletingIds.has(creator.uid);
            return (
              <motion.div
                key={creator.uid}
                layout
                whileHover={{ scale: 0.98 }}
                whileTap={{ scale: 0.96 }}
                className="bg-card rounded-[22px] apple-shadow-widget overflow-hidden cursor-pointer transition-all duration-200 group relative"
                onClick={() => navigate(`/library/${encodeURIComponent(creator.uid)}`)}
              >
                <div className={cn('aspect-square bg-gradient-to-br flex items-center justify-center relative', getGradient(i))}>
                  <span className="text-5xl font-bold text-white/90">{creator.nickname?.[0] || '?'}</span>
                  <div className="absolute top-3 right-3 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => handleSync(creator.uid, e)}
                      disabled={isSyncing || isDeleting}
                      className="w-8 h-8 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center active:scale-[0.92]"
                      title="同步"
                    >
                      {isSyncing ? (
                        <Loader2 className="size-4 text-white animate-spin" />
                      ) : (
                        <RefreshCw className="size-4 text-white" />
                      )}
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setActionMenuCreator({ uid: creator.uid, nickname: creator.nickname }); }}
                      disabled={isDeleting}
                      className="w-8 h-8 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center active:scale-[0.92]"
                      title="更多"
                    >
                      {isDeleting ? (
                        <Loader2 className="size-4 text-white animate-spin" />
                      ) : (
                        <MoreHorizontal className="size-4 text-white" />
                      )}
                    </button>
                  </div>
                </div>
                <div className="p-4">
                  <div className="font-semibold text-body truncate mb-1">{creator.nickname}</div>
                  <div className="flex items-center gap-2 text-caption text-muted-foreground">
                    <span>{creator.asset_count || 0} 个视频</span>
                    {(creator.transcript_completed_count || 0) > 0 && (
                      <span className="text-success">· {creator.transcript_completed_count} 个已转写</span>
                    )}
                    {creator.auto_sync && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-primary/10 text-primary text-[10px] font-medium">
                        自动
                      </span>
                    )}
                  </div>
                  <div className="text-caption text-muted-foreground mt-0.5">
                    {creator.last_fetch_time
                      ? new Date(creator.last_fetch_time).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
                      : '未同步'}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Creator Action Menu Modal */}
      <AnimatePresence>
        {actionMenuCreator && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm"
            onClick={() => setActionMenuCreator(null)}
          >
            <motion.div
              initial={{ y: '100%', opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: '100%', opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="bg-card rounded-t-[22px] sm:rounded-[22px] w-full sm:w-full sm:max-w-sm sm:mx-4 shadow-xl overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-4 border-b border-border/40">
                <div className="text-sm font-semibold truncate">{actionMenuCreator.nickname}</div>
              </div>
              <div className="p-2">
                <button
                  onClick={() => {
                    handleSync(actionMenuCreator.uid, { stopPropagation: () => {} } as React.MouseEvent);
                    setActionMenuCreator(null);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-secondary transition-colors text-left"
                >
                  <RefreshCw className="size-4 text-primary" />
                  <span className="text-sm">立即同步</span>
                </button>
                <div className="h-px bg-border/40 my-1" />
                <div className="w-full flex items-center justify-between px-4 py-3">
                  <span className="text-sm">自动同步</span>
                  <Switch
                    checked={!!allCreators.find((c) => c.uid === actionMenuCreator.uid)?.auto_sync}
                    onCheckedChange={() => handleToggleAutoSync(actionMenuCreator.uid)}
                  />
                </div>
                <div className="h-px bg-border/40 my-1" />
                <button
                  onClick={() => handleDeleteCreator(actionMenuCreator.uid)}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-destructive/10 transition-colors text-left"
                >
                  <Trash2 className="size-4 text-destructive" />
                  <span className="text-sm text-destructive">删除创作者</span>
                </button>
              </div>
              <div className="p-2 border-t border-border/40">
                <button
                  onClick={() => setActionMenuCreator(null)}
                  className="w-full py-3 rounded-xl bg-secondary text-sm font-medium hover:bg-secondary/80 transition-colors"
                >
                  取消
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Delete Creator Confirm Dialog */}
      <AnimatePresence>
        {deleteConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm px-4"
            onClick={() => setDeleteConfirm(null)}
          >
            <motion.div
              initial={{ scale: 0.92, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.92, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              className="bg-card rounded-[22px] p-6 w-full max-w-sm shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-destructive/10 flex items-center justify-center">
                  <Trash2 className="size-5 text-destructive" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold">删除创作者</h3>
                  <p className="text-sm text-muted-foreground">{deleteConfirm.nickname}</p>
                </div>
              </div>

              {deleteConfirm.assetCount > 0 && (
                <div className="mb-5 space-y-3">
                  <p className="text-sm text-muted-foreground">
                    该创作者关联 <span className="font-semibold text-foreground">{deleteConfirm.assetCount}</span> 个素材
                  </p>
                  <label className="flex items-center gap-3 p-3 rounded-xl bg-secondary/50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={deleteConfirm.deleteAssets}
                      onChange={(e) => setDeleteConfirm({ ...deleteConfirm, deleteAssets: e.target.checked })}
                      className="size-4 rounded border-border accent-destructive"
                    />
                    <span className="text-sm">连同素材一起删除</span>
                  </label>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  onClick={() => setDeleteConfirm(null)}
                  className="flex-1 py-2.5 rounded-xl bg-secondary text-sm font-medium hover:bg-secondary/80 transition-colors active:scale-[0.96]"
                >
                  取消
                </button>
                <button
                  onClick={executeDeleteCreator}
                  disabled={deletingIds.has(deleteConfirm.uid)}
                  className="flex-1 py-2.5 rounded-xl bg-destructive text-destructive-foreground text-sm font-medium hover:bg-destructive/90 transition-colors active:scale-[0.96] disabled:opacity-50"
                >
                  {deletingIds.has(deleteConfirm.uid) ? (
                    <span className="flex items-center justify-center gap-2">
                      <Loader2 className="size-4 animate-spin" />
                      删除中...
                    </span>
                  ) : (
                    deleteConfirm.deleteAssets ? '删除创作者及素材' : '仅删除创作者'
                  )}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Transcript Reader Overlay */}
      <AnimatePresence>
        {readingAsset && (
          <TranscriptReader
            asset={readingAsset}
            content={readingContent}
            loading={readingLoading}
            onClose={() => {
              setReadingAsset(null);
              setReadingContent('');
            }}
            onAssetUpdate={(updated) => {
              setRecentTranscripts((prev) =>
                prev.map((a) => (a.asset_id === updated.asset_id ? { ...a, ...updated } : a))
              );
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
