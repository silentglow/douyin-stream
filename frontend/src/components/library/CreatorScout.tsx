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
import { AnimatePresence, motion } from 'framer-motion';

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

      {/* ═══ PREVIEW DRAWER (AnimatePresence Overlay) ══════════════ */}
      <AnimatePresence>
        {active && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-xs"
            onClick={reset}
          >
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 28, stiffness: 260 }}
              className="w-full max-w-[720px] bg-[var(--background-paper)] border-l border-[var(--border-strong)] shadow-2xl h-full flex flex-col overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-[var(--color-hairline)] bg-[var(--background-vellum)]">
                <div>
                  <span className="eyebrow">Scout 探测预览</span>
                  <h3 className="font-display text-[18px] text-[var(--color-bone)] leading-tight mt-1">
                    {creatorName || '单视频/主页预览'}
                  </h3>
                </div>
                <button
                  onClick={reset}
                  className="w-8 h-8 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 text-[var(--color-smoke)] hover:text-[var(--color-bone)] flex items-center justify-center transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Scrollable List */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {linkInfo && (
                  <DirectLinkCard
                    linkInfo={linkInfo}
                    url={url}
                    submitting={submitting}
                    onDirectDownload={handleDirectDownload}
                    onDirectTranscribe={handleDirectTranscribe}
                    onCollect={handleCollect}
                    collecting={collecting}
                  />
                )}

                {videos.length > 0 && (
                  <>
                    <div className="flex items-center justify-between pb-3 border-b border-[var(--color-hairline-strong)]">
                      <span className="text-[12px] text-[var(--color-ash)]">
                        共发现 <span className="font-sans font-bold text-[16px] text-[var(--color-rust)] tabular">{totalCount}</span> 段视频可挑选
                      </span>
                      <div className="flex items-center gap-3">
                        {selectedCount > 0 && selectedCount < totalCount && (
                          <button onClick={selectAll} className="draw-line text-[11px] text-[var(--color-ash)] hover:text-[var(--color-rust)]">全选</button>
                        )}
                        {selectedCount > 0 && (
                          <button onClick={clearSelection} className="draw-line text-[11px] text-[var(--color-ash)] hover:text-[var(--color-rust)]">清除选择</button>
                        )}
                        <button
                          onClick={handleCollect}
                          disabled={collecting}
                          className="btn-sharp btn-primary py-1.5 px-3 text-[12px] flex items-center gap-1"
                        >
                          {collecting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                          收录追踪创作者
                        </button>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {videos.map((video) => {
                        const isSelected = selectedIds.has(video.aweme_id);
                        return (
                          <button
                            key={video.aweme_id}
                            onClick={() => toggleSelect(video.aweme_id)}
                            className={cn(
                              'relative p-4 text-left transition-all duration-200 group rounded-[16px] border cursor-pointer flex flex-col justify-between min-h-[140px]',
                              isSelected
                                ? 'bg-[rgba(0,113,227,0.04)] border-[var(--color-rust)] shadow-[0_4px_12px_rgba(0,113,227,0.04)]'
                                : 'bg-[var(--color-paper)] border-black/[0.04] dark:border-white/[0.04] hover:border-black/[0.08] dark:hover:border-white/[0.08] hover:shadow-[0_4px_12px_rgba(0,0,0,0.06)]'
                            )}
                          >
                            <div className="w-full">
                              <div className="flex justify-between items-start mb-2">
                                <span className="mono-cap text-[9px] opacity-60">#{video.aweme_id.slice(0, 8)}</span>
                                <div className={cn(
                                  'w-4 h-4 rounded-full border flex items-center justify-center transition-all duration-200 shrink-0',
                                  isSelected
                                    ? 'bg-[var(--color-rust)] border-[var(--color-rust)]'
                                    : 'border-[var(--color-hairline-strong)] group-hover:border-[var(--color-ash)]'
                                )}>
                                  {isSelected && <Check className="w-2.5 h-2.5 text-white" strokeWidth={3.5} />}
                                </div>
                              </div>
                              <div className="font-sans text-[13px] font-semibold leading-snug text-[var(--color-bone)] line-clamp-3 mb-2">
                                {video.desc || '未命名'}
                              </div>
                            </div>
                            <div className="pt-2 border-t border-[var(--color-hairline-faint)] flex items-baseline justify-between w-full">
                              <span className="mono-cap text-[10px]">
                                {new Date(video.create_time * 1000).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })}
                              </span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>

              {/* Sticky cherry-pick action bar */}
              {selectedCount > 0 && (
                <div className="shrink-0 px-6 py-4 bg-[var(--background-vellum)] border-t border-[var(--color-hairline-strong)] flex items-center justify-between shadow-inner">
                  <div>
                    <div className="eyebrow mb-0.5">待派发一次性任务</div>
                    <div className="font-display text-[16px] text-[var(--color-bone)]">已选 {selectedCount} 段视频</div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={handleDownloadOnly} disabled={submitting} className="btn-sharp py-1.5 px-3 text-[12.5px] flex items-center gap-1.5">
                      {submitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                      仅下载
                    </button>
                    <button onClick={handleDownloadAndTranscribe} disabled={submitting} className="btn-sharp btn-primary py-1.5 px-3 text-[12.5px] flex items-center gap-1.5">
                      {submitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <FileAudio className="w-3 h-3" />}
                      下载 + 转写
                    </button>
                  </div>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
