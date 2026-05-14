import { useMemo, useState, useCallback, useEffect } from 'react';
import { Search, Users, Plus, Loader2 } from 'lucide-react';
import { useStore } from '@/store/useStore';
import { AppleEmptyState } from '@/components/ui/AppleEmptyState';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { addCreator } from '@/lib/api';

const gradients = [
  'from-[#667eea] to-[#764ba2]',
  'from-[#f093fb] to-[#f5576c]',
  'from-[#4facfe] to-[#00f2fe]',
  'from-[#43e97b] to-[#38f9d7]',
  'from-[#fa709a] to-[#fee140]',
  'from-[#a8edea] to-[#fed6e3]',
  'from-[#ff9a9e] to-[#fecfef]',
  'from-[#667eea] to-[#764ba2]',
];

function getGradient(index: number) {
  return gradients[index % gradients.length];
}

type FilterType = 'all' | 'video' | 'transcript';

export default function Library() {
  const settings = useStore((state) => state.settings);
  const allCreators = useStore((state) => state.creators);
  const storeFetchCreators = useStore((state) => state.fetchCreators);

  const creators = useMemo(
    () => allCreators.filter((c) => c.platform !== 'local' && !c.uid.startsWith('local:')),
    [allCreators]
  );

  const [filter, setFilter] = useState<FilterType>('all');
  const [search, setSearch] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [loading, setLoading] = useState(true);

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
          className="flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground"
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

      {!douyinReady && !bilibiliReady && (
        <div className="text-xs text-muted-foreground mb-4">
          先在设置页配置抖音或 B站 Cookie 才能添加创作者
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
          {filteredCreators.map((creator, i) => (
            <div
              key={creator.uid}
              className="bg-card rounded-[22px] shadow-[0_2px_12px_rgba(0,0,0,0.06),0_0_1px_rgba(0,0,0,0.04)] overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-[0_4px_20px_rgba(0,0,0,0.1)] active:scale-[0.97]"
              onClick={() => toast.info(`${creator.nickname} 的详情页开发中`)}
            >
              <div className={cn('aspect-square bg-gradient-to-br flex items-center justify-center', getGradient(i))}>
                <span className="text-5xl font-bold text-white/90">{creator.nickname?.[0] || '?'}</span>
              </div>
              <div className="p-4">
                <div className="font-semibold text-[16px] truncate mb-1">{creator.nickname}</div>
                <div className="text-[13px] text-muted-foreground">
                  {creator.asset_count || 0} 个视频 · {creator.last_fetch_time
                    ? new Date(creator.last_fetch_time).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
                    : '未同步'}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
