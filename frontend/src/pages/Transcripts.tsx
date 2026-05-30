import { useEffect, useState, useCallback, useMemo } from 'react';
import { FileText, Star, Loader2, Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getTranscripts, getAssetTranscript } from '@/lib/api';
import { TranscriptReader } from '@/components/ui/TranscriptReader';
import { useStore } from '@/store/useStore';
import type { Asset } from '@/types';

type TranscriptItem = {
  asset_id: string;
  title: string;
  creator_uid: string;
  creator_name: string | null;
  create_time: string;
  is_read: boolean;
  is_starred: boolean;
  transcript_status: string;
  transcript_path: string;
  transcript_preview?: string;
};

export default function Transcripts() {
  const [items, setItems] = useState<TranscriptItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'unread' | 'starred'>('all');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [readingAsset, setReadingAsset] = useState<Asset | null>(null);
  const [readingContent, setReadingContent] = useState('');
  const [readingFormat, setReadingFormat] = useState<'markdown' | 'text'>('markdown');
  const [readingLoading, setReadingLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const lastCompletedTaskTime = useStore((state) => state.lastCompletedTaskTime);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    getTranscripts(filter, controller.signal)
      .then((res) => { if (!controller.signal.aborted) setItems(res.items || []); })
      .catch(() => { /* ignore */ })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); };
  }, [filter, lastCompletedTaskTime, refreshKey]);

  const handleOpenTranscript = useCallback(async (item: TranscriptItem) => {
    setSelectedId(item.asset_id);
    const asset: Asset = {
      asset_id: item.asset_id,
      title: item.title,
      creator_uid: item.creator_uid,
      video_status: 'completed',
      transcript_status: item.transcript_status,
      transcript_path: item.transcript_path,
      is_read: item.is_read,
      is_starred: item.is_starred,
      create_time: item.create_time,
    };
    setReadingAsset(asset);
    setReadingLoading(true);
    setReadingContent('');
    try {
      const content = await getAssetTranscript(item.asset_id);
      setReadingContent(content || '');
      setReadingFormat(item.transcript_path?.endsWith('.md') ? 'markdown' : 'text');
    } catch { /* ignore */ }
    finally { setReadingLoading(false); }
  }, []);

  const unreadCount = useMemo(() => items.filter((i) => !i.is_read).length, [items]);
  const starredCount = useMemo(() => items.filter((i) => i.is_starred).length, [items]);

  const filteredItems = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((i) =>
      i.title?.toLowerCase().includes(q) ||
      i.creator_name?.toLowerCase().includes(q)
    );
  }, [items, search]);

  return (
    <div className="h-full flex page-enter">
      {/* ═══ LEFT — LIST ════════════════════════════════════════ */}
      <aside className="w-[420px] flex-shrink-0 flex flex-col border-r border-[var(--color-hairline)] bg-[var(--color-paper)]/40">
        {/* Masthead */}
        <div className="px-6 pt-8 pb-5 border-b border-[var(--color-hairline)] flex-shrink-0">
          <div className="eyebrow mb-2">{items.length} 篇 · {unreadCount} 未读 · {starredCount} 收藏</div>
          <h1 className="font-display text-[44px] leading-[1] tracking-display text-[var(--color-bone)]">
            文稿库
          </h1>
        </div>

        {/* Filter + search */}
        <div className="px-6 py-4 border-b border-[var(--color-hairline)] flex-shrink-0 space-y-4">
          <div className="flex items-center gap-1">
            {(['all', 'unread', 'starred'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cn(
                  'px-3 py-1.5 text-[12px] font-medium transition-colors border-b',
                  filter === f
                    ? 'text-[var(--color-rust)] border-[var(--color-rust)]'
                    : 'text-[var(--color-smoke)] hover:text-[var(--color-bone)] border-transparent'
                )}
              >
                {f === 'all' ? '全部' : f === 'unread' ? '未读' : '收藏'}
                {f === 'unread' && unreadCount > 0 && (
                  <span className="ml-1.5 font-display text-[14px] text-[var(--color-rust)] tabular">{unreadCount}</span>
                )}
                {f === 'starred' && starredCount > 0 && (
                  <span className="ml-1.5 font-display text-[14px] text-[var(--color-ember)] tabular">{starredCount}</span>
                )}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3 border-b border-[var(--color-hairline)] pb-2">
            <Search className="w-3.5 h-3.5 text-[var(--color-smoke)]" strokeWidth={1.5} />
            <input
              type="text"
              placeholder="搜索文稿..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1 bg-transparent text-[14px] text-[var(--color-bone)] placeholder:text-[var(--color-smoke)] outline-none"
            />
            {search && (
              <button onClick={() => setSearch('')} className="text-[var(--color-smoke)] hover:text-[var(--color-rust)]">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-4 h-4 animate-spin text-[var(--color-smoke)]" />
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="py-16 text-center px-6">
              <div className="font-display text-[24px] text-[var(--color-smoke)] mb-2">
                {search ? '无匹配' : '暂无文稿'}
              </div>
              <div className="text-[12px] text-[var(--color-ash)]">
                完成转写后将自动显示在这里
              </div>
            </div>
          ) : (
            filteredItems.map((item) => (
              <button
                key={item.asset_id}
                onClick={() => handleOpenTranscript(item)}
                className={cn(
                  'w-full text-left px-6 py-4 border-b border-[var(--color-hairline-faint)] transition-colors group relative',
                  selectedId === item.asset_id
                    ? 'bg-[rgba(255,106,47,0.06)]'
                    : 'hover:bg-[rgba(255,255,255,0.015)]'
                )}
              >
                {/* Active rail */}
                {selectedId === item.asset_id && (
                  <span className="absolute left-0 top-0 bottom-0 w-[3px] bg-[var(--color-rust)] rounded-r-full" />
                )}

                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start gap-2">
                      {item.is_starred && (
                        <Star className="w-3.5 h-3.5 text-[var(--color-ember)] fill-[var(--color-ember)] flex-shrink-0 mt-1" />
                      )}
                      <div className={cn(
                        'font-sans font-semibold text-[15px] leading-snug line-clamp-2 transition-colors',
                        selectedId === item.asset_id
                          ? 'text-[var(--color-rust)]'
                          : 'text-[var(--color-bone)] group-hover:text-[var(--color-rust)]'
                      )}>
                        {item.title || '未命名文稿'}
                      </div>
                    </div>
                    {item.transcript_preview && (
                      <div className="text-[12px] text-[var(--color-ash)] mt-2 line-clamp-2 leading-relaxed">
                        {item.transcript_preview}
                      </div>
                    )}
                    <div className="flex items-center gap-2 mt-2.5 mono-cap">
                      <span>{item.creator_name || '本地素材'}</span>
                      <span className="text-[var(--color-smoke)]">·</span>
                      <span>
                        {new Date(item.create_time).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })}
                      </span>
                    </div>
                  </div>
                  {!item.is_read && (
                    <span className="w-2 h-2 rounded-full bg-[var(--color-rust)] flex-shrink-0 mt-2 shadow-[0_0_8px_rgba(255,106,47,0.6)] animate-pulse" />
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* ═══ RIGHT — READER ═════════════════════════════════════ */}
      <div className="flex-1 flex flex-col bg-[var(--color-ink)] overflow-hidden">
        {readingAsset ? (
          <TranscriptReader
            asset={readingAsset}
            content={readingContent}
            format={readingFormat}
            loading={readingLoading}
            onClose={() => {
              setReadingAsset(null);
              setReadingContent('');
              setSelectedId(null);
              setRefreshKey((k) => k + 1);
            }}
            onAssetUpdate={(updated) => {
              setItems((prev) =>
                prev.map((i) => (i.asset_id === updated.asset_id ? { ...i, ...updated } : i))
              );
            }}
          />
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center px-10">
            <div className="font-display text-[44px] text-[var(--color-smoke)] leading-tight mb-3">
              选择一篇文稿
            </div>
            <div className="text-[13px] text-[var(--color-ash)]">
              左侧显示所有已完成的转写
            </div>
            <FileText className="w-4 h-4 text-[var(--color-smoke)] mt-6 opacity-40" strokeWidth={1.5} />
          </div>
        )}
      </div>
    </div>
  );
}
