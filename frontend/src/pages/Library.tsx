import { useMemo, useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Users, Plus, Loader2, RefreshCw, FileAudio, X, ArrowRight } from 'lucide-react';
import { useStore } from '@/store/useStore';
import { AppleEmptyState } from '@/components/ui/AppleEmptyState';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { addCreator, triggerCreatorDownload } from '@/lib/api';
import { selectFolder, scanDirectory, triggerLocalTranscribe } from '@/lib/api';

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

  // Local transcribe state
  const [localTranscribeOpen, setLocalTranscribeOpen] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scannedFiles, setScannedFiles] = useState<Array<{ path: string; name: string }>>([]);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [transcribing, setTranscribing] = useState(false);
  const [scannedDirectory, setScannedDirectory] = useState('');

  useEffect(() => {
    storeFetchCreators().then(() => setLoading(false));
  }, [storeFetchCreators]);

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
                <span className="text-sm truncate">{file.name}</span>
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
            return (
              <div
                key={creator.uid}
                className="bg-card rounded-[22px] apple-shadow-widget overflow-hidden cursor-pointer transition-all duration-200 active:scale-[0.97] group"
                onClick={() => navigate(`/library/${encodeURIComponent(creator.uid)}`)}
              >
                <div className={cn('aspect-square bg-gradient-to-br flex items-center justify-center relative', getGradient(i))}>
                  <span className="text-5xl font-bold text-white/90">{creator.nickname?.[0] || '?'}</span>
                  <button
                    onClick={(e) => handleSync(creator.uid, e)}
                    disabled={isSyncing}
                    className="absolute bottom-3 right-3 w-8 h-8 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity active:scale-[0.92]"
                    title="同步"
                  >
                    {isSyncing ? (
                      <Loader2 className="size-4 text-white animate-spin" />
                    ) : (
                      <RefreshCw className="size-4 text-white" />
                    )}
                  </button>
                </div>
                <div className="p-4">
                  <div className="font-semibold text-body truncate mb-1">{creator.nickname}</div>
                  <div className="text-caption text-muted-foreground">
                    {creator.asset_count || 0} 个视频 · {creator.last_fetch_time
                      ? new Date(creator.last_fetch_time).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
                      : '未同步'}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
