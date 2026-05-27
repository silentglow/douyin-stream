import { useState, useCallback } from 'react';
import { Link2, Loader2, AlertCircle, Check, Download, FileAudio } from 'lucide-react';
import { toast } from 'sonner';
import { fetchMetadata, triggerPipeline, triggerBatchPipeline, triggerDownloadBatch } from '@/lib/api';
import type { DouyinVideoMeta } from '@/types';
import { LinkInfo, detectLinkType } from '@/components/discover/discoverUtils';
import { DirectLinkCard } from '@/components/discover/DirectLinkCard';
import { cn } from '@/lib/utils';

export default function Discover() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [videos, setVideos] = useState<DouyinVideoMeta[]>([]);
  const [creatorName, setCreatorName] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [linkInfo, setLinkInfo] = useState<LinkInfo | null>(null);

  const handleFetch = useCallback(async () => {
    if (!url.trim()) { toast.error('请输入链接'); return; }
    if (!url.trim().startsWith('http')) { toast.error('请输入有效的链接'); return; }

    setLoading(true);
    setError('');
    setVideos([]);
    setSelectedIds(new Set());
    setCreatorName('');
    setLinkInfo(null);

    const detected = detectLinkType(url.trim());
    if (!detected) {
      setError('不支持的链接格式，目前支持抖音和 B 站');
      setLoading(false);
      return;
    }

    if (detected.platform === 'douyin' && detected.type === 'profile') {
      try {
        const res = await fetchMetadata(url.trim(), 20);
        setVideos(res.videos || []);
        setCreatorName(res.creator?.nickname || '');
        if ((res.videos || []).length === 0) {
          toast.info('未找到视频，请检查链接');
        } else {
          toast.success(`找到 ${res.videos.length} 个视频`);
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : '获取失败，请检查链接有效性';
        setError(message);
      } finally {
        setLoading(false);
      }
    } else {
      setLinkInfo(detected);
      setLoading(false);
      toast.success('检测到视频链接，可直接下载');
    }
  }, [url]);

  const handleDirectDownload = useCallback(async () => {
    if (!url.trim()) return;
    setSubmitting(true);
    try {
      const res = await triggerDownloadBatch([url.trim()]);
      toast.success('下载任务已派发', { description: `id: ${res.task_id.slice(0, 8)}` });
    } catch { /* */ } finally { setSubmitting(false); }
  }, [url]);

  const handleDirectTranscribe = useCallback(async () => {
    if (!url.trim()) return;
    setSubmitting(true);
    try {
      const maxCounts = linkInfo?.type === 'up_space' ? 20 : 1;
      const res = await triggerPipeline(url.trim(), maxCounts);
      toast.success('下载 + 转写任务已派发', { description: `id: ${res.task_id.slice(0, 8)}` });
    } catch { /* */ } finally { setSubmitting(false); }
  }, [url, linkInfo]);

  const toggleSelect = useCallback((awemeId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(awemeId)) next.delete(awemeId);
      else next.add(awemeId);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => setSelectedIds(new Set(videos.map((v) => v.aweme_id))), [videos]);
  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const handleDownloadOnly = useCallback(async () => {
    if (selectedIds.size === 0) { toast.error('请先选择视频'); return; }
    const selectedUrls = videos.filter((v) => selectedIds.has(v.aweme_id)).map((v) => v.video_url);
    setSubmitting(true);
    try {
      const res = await triggerDownloadBatch(selectedUrls);
      toast.success('下载任务已派发', { description: `id: ${res.task_id.slice(0, 8)}` });
      setSelectedIds(new Set());
    } catch { /* */ } finally { setSubmitting(false); }
  }, [selectedIds, videos]);

  const handleDownloadAndTranscribe = useCallback(async () => {
    if (selectedIds.size === 0) { toast.error('请先选择视频'); return; }
    const selectedUrls = videos.filter((v) => selectedIds.has(v.aweme_id)).map((v) => v.video_url);
    setSubmitting(true);
    try {
      const res = await triggerBatchPipeline(selectedUrls);
      toast.success('下载 + 转写任务已派发', { description: `id: ${res.task_id.slice(0, 8)}` });
      setSelectedIds(new Set());
    } catch { /* */ } finally { setSubmitting(false); }
  }, [selectedIds, videos]);

  const handlePasteFromClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text.trim()) setUrl(text.trim());
    } catch { toast.error('无法读取剪贴板'); }
  }, []);

  const selectedCount = selectedIds.size;
  const totalCount = videos.length;

  return (
    <div className="h-full overflow-y-auto page-enter">      <header className="px-10 pt-12 pb-9 border-b border-[var(--color-hairline)]">
        <div className="flex items-end justify-between gap-10">
          <div>
            <div className="eyebrow mb-4">勘察新内容</div>
            <h1 className="font-display text-[clamp(48px,6.5vw,96px)] leading-[0.95] tracking-display text-[var(--color-bone)]">
              发现
            </h1>
            <p className="mt-4 text-[15px] leading-[1.55] text-[var(--color-ash)] max-w-xl">
              粘贴博主主页链接预览作品，或直接粘贴视频链接快速下载 / 转写。支持抖音和 B 站。
            </p>
          </div>
        </div>
      </header>
      <section className="px-10 py-6 border-b border-[var(--color-hairline)]">
        <div className="flex items-center gap-4 max-w-4xl">
          <div className="flex-1 flex items-center gap-3 border-b border-[var(--color-hairline)] pb-2 focus-within:border-[var(--color-rust)] transition-colors">
            <Link2 className="w-3.5 h-3.5 text-[var(--color-smoke)]" strokeWidth={1.5} />
            <input
              type="text"
              placeholder="抖音主页 / 视频链接，或 B 站视频链接"
              value={url}
              onChange={(e) => { setUrl(e.target.value); setError(''); }}
              onKeyDown={(e) => { if (e.key === 'Enter') handleFetch(); }}
              className="flex-1 bg-transparent font-mono text-[14px] text-[var(--color-bone)] placeholder:text-[var(--color-smoke)] outline-none"
            />
          </div>
          <button onClick={handlePasteFromClipboard} className="btn-sharp">粘贴</button>
          <button
            onClick={handleFetch}
            disabled={loading || !url.trim()}
            className="btn-sharp btn-primary disabled:opacity-40 flex items-center gap-2"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            预览
          </button>
        </div>
        {error && (
          <div className="flex items-center gap-2 mt-4 text-[13px] text-[var(--color-iron)]">
            <AlertCircle className="w-4 h-4" />
            {error}
          </div>
        )}
      </section>
      <div className="px-10 py-10">
        {linkInfo && (
          <DirectLinkCard
            linkInfo={linkInfo}
            url={url}
            submitting={submitting}
            onDirectDownload={handleDirectDownload}
            onDirectTranscribe={handleDirectTranscribe}
          />
        )}

        {videos.length > 0 && (
          <>
            <div className="flex items-baseline justify-between mb-6 pb-3 border-b border-[var(--color-hairline-strong)]">
              <div>
                <h2 className="font-display text-[28px] text-[var(--color-bone)] leading-none">
                  {creatorName || '未命名创作者'}
                </h2>
                <div className="text-[12px] text-[var(--color-ash)] mt-2">
                  共 <span className="font-display text-[18px] text-[var(--color-rust)] tabular">{totalCount}</span> 段可预览
                </div>
              </div>
              <div className="flex items-center gap-4">
                {selectedCount > 0 && selectedCount < totalCount && (
                  <button onClick={selectAll} className="draw-line text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)]">全选</button>
                )}
                {selectedCount > 0 && (
                  <button onClick={clearSelection} className="draw-line text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)]">清除</button>
                )}
                {selectedCount > 0 && (
                  <span className="text-[13px] text-[var(--color-ash)]">
                    已选 <span className="font-display text-[20px] text-[var(--color-rust)] tabular mx-1">{selectedCount}</span> / {totalCount}
                  </span>
                )}
              </div>
            </div>

            {/* Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5 stagger">
              {videos.map((video) => {
                const isSelected = selectedIds.has(video.aweme_id);
                return (
                  <button
                    key={video.aweme_id}
                    onClick={() => toggleSelect(video.aweme_id)}
                    className={cn(
                      'relative aspect-[4/5] p-6 text-left transition-all duration-300 group rounded-[var(--radius-card)] border cursor-pointer flex flex-col justify-between',
                      isSelected
                        ? 'bg-[rgba(99,102,241,0.04)] border-[var(--color-rust)] shadow-[0_8px_30px_rgba(99,102,241,0.08)]'
                        : 'bg-[var(--color-paper)] border-white/[0.03] hover:border-white/[0.08] hover:shadow-[0_8px_30px_rgba(0,0,0,0.15)] hover:-translate-y-0.5'
                    )}
                  >
                    <div>
                      {/* Header — checkbox only */}
                      <div className="flex justify-end mb-3">
                        <div className={cn(
                          'w-5 h-5 rounded-full border flex items-center justify-center transition-all duration-200',
                          isSelected
                            ? 'bg-[var(--color-rust)] border-[var(--color-rust)]'
                            : 'border-[var(--color-hairline-strong)] group-hover:border-[var(--color-ash)]'
                        )}>
                          {isSelected && <Check className="w-3.5 h-3.5 text-[var(--color-ink)]" strokeWidth={3.5} />}
                        </div>
                      </div>

                      {/* Title */}
                      <div className="font-sans text-[14.5px] font-semibold leading-snug text-[var(--color-bone)] line-clamp-4 mb-4">
                        {video.desc || '未命名'}
                      </div>
                    </div>

                    {/* Footer */}
                    <div className="pt-3 border-t border-[var(--color-hairline-faint)] flex items-baseline justify-between w-full">
                      <span className="mono-cap">
                        {new Date(video.create_time * 1000).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })}
                      </span>
                      {isSelected && (
                        <span className="text-[11px] tracking-[0.16em] uppercase text-[var(--color-rust)] font-bold">已选</span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Action bar — sticky */}
            {selectedCount > 0 && (
              <div className="sticky bottom-0 mt-8 -mx-10 px-10 py-5 bg-[var(--color-paper)]/95 backdrop-blur-xl border-t border-[var(--color-hairline-strong)] flex items-center justify-between">
                <div>
                  <div className="eyebrow mb-1">待派发</div>
                  <div className="font-display text-[22px] text-[var(--color-bone)]">
                    已选 {selectedCount} 段
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleDownloadOnly}
                    disabled={submitting}
                    className="btn-sharp disabled:opacity-40 flex items-center gap-2"
                  >
                    {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                    仅下载
                  </button>
                  <button
                    onClick={handleDownloadAndTranscribe}
                    disabled={submitting}
                    className="btn-sharp btn-primary disabled:opacity-40 flex items-center gap-2"
                  >
                    {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileAudio className="w-3.5 h-3.5" />}
                    下载 + 转写
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        {/* Empty State */}
        {videos.length === 0 && !loading && !error && !linkInfo && (
          <div className="py-32 text-center max-w-md mx-auto">
            <div className="font-display text-[36px] text-[var(--color-smoke)] leading-tight mb-3">
              等待勘察
            </div>
            <div className="text-[13px] text-[var(--color-ash)]">
              粘贴抖音主页 / 视频链接，或 B 站视频链接以开始
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
