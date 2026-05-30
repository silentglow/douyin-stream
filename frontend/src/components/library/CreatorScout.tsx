import { useState, useCallback, useEffect } from 'react';
import { Link2, Loader2, AlertCircle, Check, Download, FileAudio, Plus, X } from 'lucide-react';
import { toast } from 'sonner';
import {
  fetchMetadata, addCreator, triggerPipeline, triggerBatchPipeline, triggerDownloadBatch,
} from '@/lib/api';
import { useStore } from '@/store/useStore';
import type { DouyinVideoMeta } from '@/types';
import { LinkInfo, detectLinkType } from '@/components/discover/discoverUtils';
import { DirectLinkCard } from '@/components/discover/DirectLinkCard';
import { cn } from '@/lib/utils';

interface CreatorScoutProps {
  /** Fired when the preview area opens/closes, so the host can hide its roster while scouting. */
  onActiveChange?: (active: boolean) => void;
  /** Fired after a creator is collected, so the host can refresh its roster. */
  onCollected?: () => void;
}

/**
 * Paste a creator URL → preview their videos → either 收录追踪 (track the whole creator)
 * or 挑选 N 条 (cherry-pick specific videos to download / transcribe).
 * Single video / B站 links resolve to a DirectLinkCard for one-off download.
 */
export function CreatorScout({ onActiveChange, onCollected }: CreatorScoutProps) {
  const storeFetchCreators = useStore((s) => s.fetchCreators);

  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [videos, setVideos] = useState<DouyinVideoMeta[]>([]);
  const [creatorName, setCreatorName] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState('');
  const [linkInfo, setLinkInfo] = useState<LinkInfo | null>(null);

  const active = videos.length > 0 || !!linkInfo;
  useEffect(() => { onActiveChange?.(active); }, [active, onActiveChange]);

  const reset = useCallback(() => {
    setUrl('');
    setVideos([]);
    setSelectedIds(new Set());
    setCreatorName('');
    setLinkInfo(null);
    setError('');
  }, []);

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
        if ((res.videos || []).length === 0) toast.info('未找到视频，请检查链接');
        else toast.success(`找到 ${res.videos.length} 个视频`);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '获取失败，请检查链接有效性');
      } finally {
        setLoading(false);
      }
    } else {
      setLinkInfo(detected);
      setLoading(false);
      toast.success('检测到视频链接，可直接下载');
    }
  }, [url]);

  const handleCollect = useCallback(async () => {
    if (!url.trim()) return;
    setCollecting(true);
    try {
      await addCreator(url.trim());
      toast.success('创作者已收录');
      reset();
      await storeFetchCreators(true);
      onCollected?.();
    } catch { /* api interceptor handles toast */ }
    finally { setCollecting(false); }
  }, [url, reset, storeFetchCreators, onCollected]);

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
      if (next.has(awemeId)) next.delete(awemeId); else next.add(awemeId);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => setSelectedIds(new Set(videos.map((v) => v.aweme_id))), [videos]);
  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const handleDownloadOnly = useCallback(async () => {
    if (selectedIds.size === 0) { toast.error('请先选择视频'); return; }
    const urls = videos.filter((v) => selectedIds.has(v.aweme_id)).map((v) => v.video_url);
    setSubmitting(true);
    try {
      const res = await triggerDownloadBatch(urls);
      toast.success('下载任务已派发', { description: `id: ${res.task_id.slice(0, 8)}` });
      setSelectedIds(new Set());
    } catch { /* */ } finally { setSubmitting(false); }
  }, [selectedIds, videos]);

  const handleDownloadAndTranscribe = useCallback(async () => {
    if (selectedIds.size === 0) { toast.error('请先选择视频'); return; }
    const urls = videos.filter((v) => selectedIds.has(v.aweme_id)).map((v) => v.video_url);
    setSubmitting(true);
    try {
      const res = await triggerBatchPipeline(urls);
      toast.success('下载 + 转写任务已派发', { description: `id: ${res.task_id.slice(0, 8)}` });
      setSelectedIds(new Set());
    } catch { /* */ } finally { setSubmitting(false); }
  }, [selectedIds, videos]);

  const handlePasteFromClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text.trim()) { setUrl(text.trim()); setError(''); }
    } catch { toast.error('无法读取剪贴板'); }
  }, []);

  const selectedCount = selectedIds.size;
  const totalCount = videos.length;

  return (
    <div>
      {/* ═══ PASTE BAR ═══════════════════════════════════════════ */}
      <section className="px-10 py-5 border-b border-[var(--color-hairline)]">
        <div className="flex items-center gap-4">
          <div className="flex-1 flex items-center gap-3 border-b border-[var(--color-hairline)] pb-2 focus-within:border-[var(--color-rust)] transition-colors">
            <Link2 className="w-3.5 h-3.5 text-[var(--color-smoke)]" strokeWidth={1.5} />
            <input
              id="add-creator-input"
              type="text"
              placeholder="粘贴创作者主页链接预览收录，或视频链接直接下载（抖音 / B 站）"
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
          {active && (
            <button onClick={reset} className="btn-sharp flex items-center gap-1.5" title="清除预览">
              <X className="w-3.5 h-3.5" />
              收起
            </button>
          )}
        </div>
        {error && (
          <div className="flex items-center gap-2 mt-4 text-[13px] text-[var(--color-iron)]">
            <AlertCircle className="w-4 h-4" />
            {error}
          </div>
        )}
      </section>

      {/* ═══ SINGLE-LINK CARD ════════════════════════════════════ */}
      {linkInfo && (
        <div className="px-10 py-8 border-b border-[var(--color-hairline)]">
          <DirectLinkCard
            linkInfo={linkInfo}
            url={url}
            submitting={submitting}
            onDirectDownload={handleDirectDownload}
            onDirectTranscribe={handleDirectTranscribe}
          />
        </div>
      )}

      {/* ═══ CREATOR PREVIEW ═════════════════════════════════════ */}
      {videos.length > 0 && (
        <div className="px-10 py-8 border-b border-[var(--color-hairline)]">
          {/* Header: identity + the two intents */}
          <div className="flex items-end justify-between gap-6 mb-6 pb-3 border-b border-[var(--color-hairline-strong)]">
            <div>
              <div className="eyebrow mb-2">预览 · 未收录</div>
              <h2 className="font-display text-[28px] text-[var(--color-bone)] leading-none">
                {creatorName || '未命名创作者'}
              </h2>
              <div className="text-[12px] text-[var(--color-ash)] mt-2">
                共 <span className="font-display text-[18px] text-[var(--color-rust)] tabular">{totalCount}</span> 段可预览
              </div>
            </div>
            <div className="flex items-center gap-5 pb-1">
              {selectedCount > 0 && selectedCount < totalCount && (
                <button onClick={selectAll} className="draw-line text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)]">全选</button>
              )}
              {selectedCount > 0 && (
                <button onClick={clearSelection} className="draw-line text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)]">清除选择</button>
              )}
              <button
                onClick={handleCollect}
                disabled={collecting}
                className="btn-sharp btn-primary disabled:opacity-40 flex items-center gap-2"
                title="把该创作者加入名册，长期追踪同步"
              >
                {collecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                收录追踪
              </button>
            </div>
          </div>

          {/* Selectable grid */}
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
                      ? 'bg-[rgba(255,106,47,0.06)] border-[var(--color-rust)] shadow-[0_8px_30px_rgba(255,106,47,0.1)]'
                      : 'bg-[var(--color-paper)] border-white/[0.04] hover:border-white/[0.1] hover:shadow-[0_8px_30px_rgba(0,0,0,0.25)] hover:-translate-y-0.5'
                  )}
                >
                  <div>
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
                    <div className="font-sans text-[14.5px] font-semibold leading-snug text-[var(--color-bone)] line-clamp-4 mb-4">
                      {video.desc || '未命名'}
                    </div>
                  </div>
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

          {/* Sticky cherry-pick action bar */}
          {selectedCount > 0 && (
            <div className="sticky bottom-0 mt-8 -mx-10 px-10 py-5 bg-[var(--color-paper)]/95 backdrop-blur-xl border-t border-[var(--color-hairline-strong)] flex items-center justify-between">
              <div>
                <div className="eyebrow mb-1">待派发 · 一次性</div>
                <div className="font-display text-[22px] text-[var(--color-bone)]">已选 {selectedCount} 段</div>
              </div>
              <div className="flex gap-2">
                <button onClick={handleDownloadOnly} disabled={submitting} className="btn-sharp disabled:opacity-40 flex items-center gap-2">
                  {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                  仅下载
                </button>
                <button onClick={handleDownloadAndTranscribe} disabled={submitting} className="btn-sharp btn-primary disabled:opacity-40 flex items-center gap-2">
                  {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileAudio className="w-3.5 h-3.5" />}
                  下载 + 转写
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
