import { useState, useCallback } from 'react';
import { Link2, Loader2, Download, FileAudio, CheckCircle2, AlertCircle, Search, X } from 'lucide-react';
import { toast } from 'sonner';
import { fetchMetadata, triggerPipeline, triggerDownloadBatch } from '@/lib/api';
import type { DouyinVideoMeta } from '@/types';

const C = {
  blue: '#007AFF',
  green: '#34C759',
  orange: '#FF9500',
  red: '#FF3B30',
  textSecondary: '#8E8E93',
};

export default function Discover() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [videos, setVideos] = useState<DouyinVideoMeta[]>([]);
  const [creatorName, setCreatorName] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleFetch = useCallback(async () => {
    if (!url.trim()) {
      toast.error('请输入博主主页链接');
      return;
    }
    if (!url.trim().startsWith('http')) {
      toast.error('请输入有效的链接');
      return;
    }

    setLoading(true);
    setError('');
    setVideos([]);
    setSelectedIds(new Set());
    setCreatorName('');

    try {
      const res = await fetchMetadata(url.trim(), 20);
      setVideos(res.videos || []);
      setCreatorName(res.creator?.nickname || '');
      if ((res.videos || []).length === 0) {
        toast.info('未找到视频，请检查链接是否正确');
      } else {
        toast.success(`找到 ${res.videos.length} 个视频`);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取失败，请检查链接有效性';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [url]);

  const toggleSelect = useCallback((awemeId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(awemeId)) next.delete(awemeId);
      else next.add(awemeId);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedIds(new Set(videos.map((v) => v.aweme_id)));
  }, [videos]);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const handleDownloadOnly = useCallback(async () => {
    if (selectedIds.size === 0) {
      toast.error('请先选择视频');
      return;
    }
    const selectedUrls = videos
      .filter((v) => selectedIds.has(v.aweme_id))
      .map((v) => v.video_url);

    setSubmitting(true);
    try {
      const res = await triggerDownloadBatch(selectedUrls);
      toast.success('下载任务已创建', { description: `任务 ID: ${res.task_id.slice(0, 8)}...` });
      setSelectedIds(new Set());
    } catch {
      // interceptor handles toast
    } finally {
      setSubmitting(false);
    }
  }, [selectedIds, videos]);

  const handleDownloadAndTranscribe = useCallback(async () => {
    if (selectedIds.size === 0) {
      toast.error('请先选择视频');
      return;
    }
    const selectedUrls = videos
      .filter((v) => selectedIds.has(v.aweme_id))
      .map((v) => v.video_url);

    setSubmitting(true);
    try {
      const res = await triggerPipeline(selectedUrls[0], selectedUrls.length);
      toast.success('下载+转写任务已创建', { description: `任务 ID: ${res.task_id.slice(0, 8)}...` });
      setSelectedIds(new Set());
    } catch {
      // interceptor handles toast
    } finally {
      setSubmitting(false);
    }
  }, [selectedIds, videos]);

  const handlePasteFromClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text.trim()) {
        setUrl(text.trim());
      }
    } catch {
      toast.error('无法读取剪贴板');
    }
  }, []);

  const selectedCount = selectedIds.size;
  const totalCount = videos.length;

  return (
    <div className="h-full p-7 px-8 max-sm:p-4 max-sm:pb-20 overflow-y-auto">
      <div className="text-title-1 mb-6">发现与选取</div>
      <p className="text-body text-muted-foreground mb-6">
        输入博主主页链接，预览视频列表后按需下载或转写，告别盲盒式全量下载。
      </p>

      {/* URL Input */}
      <div className="rounded-[22px] border border-border/60 bg-card apple-shadow-widget p-5 mb-6">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="粘贴博主主页链接，如 https://www.douyin.com/user/..."
              value={url}
              onChange={(e) => { setUrl(e.target.value); setError(''); }}
              onKeyDown={(e) => { if (e.key === 'Enter') handleFetch(); }}
              className="w-full bg-secondary rounded-xl pl-10 pr-10 py-3 text-sm outline-none border border-transparent focus:border-primary/50"
            />
            {url && (
              <button
                onClick={() => { setUrl(''); setVideos([]); setError(''); }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
          <button
            onClick={handlePasteFromClipboard}
            className="px-4 py-3 rounded-xl text-sm font-medium bg-secondary hover:bg-secondary/80 transition-colors"
            title="从剪贴板粘贴"
          >
            粘贴
          </button>
          <button
            onClick={handleFetch}
            disabled={loading || !url.trim()}
            className="px-6 py-3 rounded-xl text-sm font-semibold text-white transition-all active:scale-[0.97] disabled:opacity-50"
            style={{ background: C.blue }}
          >
            {loading ? <Loader2 className="size-4 animate-spin" /> : '预览'}
          </button>
        </div>
        {error && (
          <div className="flex items-center gap-2 mt-3 text-sm text-destructive">
            <AlertCircle className="size-4" />
            {error}
          </div>
        )}
      </div>

      {/* Video List */}
      {videos.length > 0 && (
        <div className="rounded-[22px] border border-border/60 bg-card apple-shadow-widget overflow-hidden">
          {/* Toolbar */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-border/60">
            <div className="flex items-center gap-3">
              <span className="text-sm font-semibold text-foreground">
                {creatorName || '视频列表'}
              </span>
              <span className="text-xs text-muted-foreground">
                共 {totalCount} 个视频
              </span>
            </div>
            <div className="flex items-center gap-2">
              {selectedCount > 0 && selectedCount < totalCount && (
                <button
                  onClick={selectAll}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  全选
                </button>
              )}
              {selectedCount > 0 && (
                <button
                  onClick={clearSelection}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  取消选择
                </button>
              )}
              {selectedCount > 0 && (
                <span className="text-xs font-medium px-2 py-0.5 rounded-full" style={{ background: `${C.blue}20`, color: C.blue }}>
                  已选 {selectedCount} 个
                </span>
              )}
            </div>
          </div>

          {/* Video Grid */}
          <div className="p-4">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {videos.map((video) => {
                const isSelected = selectedIds.has(video.aweme_id);
                return (
                  <div
                    key={video.aweme_id}
                    onClick={() => toggleSelect(video.aweme_id)}
                    className={`relative rounded-xl overflow-hidden cursor-pointer transition-all active:scale-[0.98] border-2 ${
                      isSelected ? 'border-primary' : 'border-transparent hover:border-border'
                    }`}
                  >
                    {/* Cover */}
                    <div className="aspect-video bg-secondary relative">
                      {video.cover_url ? (
                        <img
                          src={video.cover_url}
                          alt={video.desc || ''}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-muted-foreground">
                          <FileAudio className="size-8" />
                        </div>
                      )}
                      {/* Selection checkbox */}
                      <div className="absolute top-2 left-2">
                        <div
                          className="w-5 h-5 rounded-md flex items-center justify-center border-2 transition-colors"
                          style={{
                            background: isSelected ? C.blue : 'rgba(0,0,0,0.3)',
                            borderColor: isSelected ? C.blue : 'rgba(255,255,255,0.5)',
                          }}
                        >
                          {isSelected && <CheckCircle2 className="size-3.5 text-white" />}
                        </div>
                      </div>
                    </div>
                    {/* Info */}
                    <div className="p-2.5 bg-card">
                      <div className="text-xs font-medium text-foreground line-clamp-2">
                        {video.desc || '未命名'}
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-1">
                        {new Date(video.create_time * 1000).toLocaleDateString('zh-CN')}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Action Bar */}
          {selectedCount > 0 && (
            <div className="flex items-center justify-between px-5 py-3 border-t border-border/60 bg-secondary/30">
              <span className="text-sm text-muted-foreground">
                已选择 {selectedCount} 个视频
              </span>
              <div className="flex gap-3">
                <button
                  onClick={handleDownloadOnly}
                  disabled={submitting}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all active:scale-[0.97] disabled:opacity-50 bg-secondary hover:bg-secondary/80"
                >
                  {submitting ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
                  仅下载
                </button>
                <button
                  onClick={handleDownloadAndTranscribe}
                  disabled={submitting}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white transition-all active:scale-[0.97] disabled:opacity-50"
                  style={{ background: C.blue }}
                >
                  {submitting ? <Loader2 className="size-4 animate-spin" /> : <FileAudio className="size-4" />}
                  下载 + 转写
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {videos.length === 0 && !loading && !error && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="flex size-20 items-center justify-center rounded-2xl bg-secondary">
            <Link2 className="size-8 text-muted-foreground/50" />
          </div>
          <p className="mt-4 text-sm font-medium text-foreground">输入博主链接开始探索</p>
          <p className="mt-1 text-xs text-muted-foreground">支持抖音博主主页链接</p>
        </div>
      )}
    </div>
  );
}
