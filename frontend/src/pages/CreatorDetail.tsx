import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, RefreshCw, Loader2, FileText, Clock, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { useStore } from '@/store/useStore';
import { getAssetsByCreator, getAssetTranscript } from '@/lib/api';
import { triggerCreatorDownload } from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import type { Asset } from '@/types';

const C = {
  blue: '#007AFF',
  green: '#34C759',
  orange: '#FF9500',
  red: '#FF3B30',
  textSecondary: '#8E8E93',
};

function StatusBadge({ status, error }: { status: string; error?: string | null }) {
  if (status === 'COMPLETED') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#34C759]">
        <CheckCircle2 className="size-3" />
        已转写
      </span>
    );
  }
  if (status === 'FAILED' || error) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#FF3B30]">
        <AlertTriangle className="size-3" />
        失败
      </span>
    );
  }
  if (status === 'PENDING' || status === 'queued') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#8E8E93]">
        <Clock className="size-3" />
        待转写
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#FF9500]">
      <Loader2 className="size-3 animate-spin" />
      {status}
    </span>
  );
}

export default function CreatorDetail() {
  const { creatorUid } = useParams<{ creatorUid: string }>();
  const navigate = useNavigate();
  const creators = useStore((s) => s.creators);

  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [viewingAsset, setViewingAsset] = useState<Asset | null>(null);
  const [transcriptContent, setTranscriptContent] = useState('');
  const [transcriptLoading, setTranscriptLoading] = useState(false);

  const creator = creators.find((c) => c.uid === creatorUid);

  useEffect(() => {
    if (!creatorUid) return;
    let cancelled = false;
    setLoading(true);
    getAssetsByCreator(decodeURIComponent(creatorUid))
      .then((data) => { if (!cancelled) setAssets(data); })
      .catch(() => { if (!cancelled) toast.error('获取素材失败'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [creatorUid]);

  const handleSync = useCallback(async () => {
    if (!creatorUid || syncing) return;
    setSyncing(true);
    try {
      await triggerCreatorDownload(decodeURIComponent(creatorUid), 'incremental');
      toast.success('同步任务已启动');
    } catch {
      // api interceptor handles toast
    } finally {
      setSyncing(false);
    }
  }, [creatorUid, syncing]);

  const handleViewTranscript = useCallback(async (asset: Asset) => {
    setViewingAsset(asset);
    setTranscriptLoading(true);
    setTranscriptContent('');
    try {
      const content = await getAssetTranscript(asset.asset_id);
      setTranscriptContent(content);
    } catch {
      toast.error('获取转写内容失败');
    } finally {
      setTranscriptLoading(false);
    }
  }, []);

  if (!creator) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-muted-foreground">创作者不存在</div>
      </div>
    );
  }

  return (
    <div className="h-full p-7 px-8 max-sm:p-4 max-sm:pb-20 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/library')}
          className="flex items-center justify-center w-9 h-9 rounded-xl bg-secondary hover:bg-secondary/80 transition-colors"
        >
          <ArrowLeft className="size-[18px] text-muted-foreground" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="text-title-1 font-bold tracking-tight truncate">{creator.nickname}</div>
          <div className="text-[13px] text-muted-foreground">
            {creator.asset_count || 0} 个视频 · {assets.filter((a) => a.transcript_status === 'COMPLETED').length} 个已转写
          </div>
        </div>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="flex items-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary/90 transition-all active:scale-[0.97] disabled:opacity-50"
        >
          {syncing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
          同步
        </button>
      </div>

      {/* Asset List */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-card rounded-[18px] h-[72px] apple-skeleton" />
          ))}
        </div>
      ) : assets.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-[60px]">
          <FileText className="size-8 text-muted-foreground/40 mb-3" />
          <div className="text-[20px] font-semibold text-[#8E8E93]">还没有素材</div>
          <div className="text-[13px] text-muted-foreground mt-1">点击上方「同步」按钮获取视频</div>
        </div>
      ) : (
        <div className="space-y-3">
          {assets.map((asset) => (
            <div
              key={asset.asset_id}
              className="bg-card rounded-[18px] shadow-[0_2px_12px_rgba(0,0,0,0.06),0_0_1px_rgba(0,0,0,0.04)] p-4 flex items-center gap-3 cursor-pointer transition-all hover:shadow-[0_4px_20px_rgba(0,0,0,0.1)] active:scale-[0.98]"
              onClick={() => {
                if (asset.transcript_status === 'COMPLETED' && asset.transcript_path) {
                  handleViewTranscript(asset);
                }
              }}
            >
              <div className="w-10 h-10 rounded-xl bg-secondary flex items-center justify-center shrink-0">
                <FileText className="size-5" style={{ color: asset.transcript_status === 'COMPLETED' ? C.green : C.textSecondary }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate text-foreground">{asset.title || '未命名视频'}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  <StatusBadge status={asset.transcript_status} error={asset.transcript_last_error} />
                  {asset.create_time && (
                    <span className="text-[11px] text-muted-foreground">
                      {new Date(asset.create_time).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}
                    </span>
                  )}
                </div>
              </div>
              {asset.transcript_status === 'COMPLETED' && (
                <span className="text-[11px] text-muted-foreground shrink-0">查看转写</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Transcript Modal */}
      {viewingAsset && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setViewingAsset(null)}
        >
          <div
            className="bg-card rounded-t-[22px] sm:rounded-[22px] w-full sm:w-full sm:max-w-2xl sm:mx-4 max-h-[85vh] flex flex-col shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-5 border-b border-border/40">
              <h3 className="text-[17px] font-semibold truncate pr-4">{viewingAsset.title || '转写内容'}</h3>
              <button
                onClick={() => setViewingAsset(null)}
                className="p-1.5 rounded-lg hover:bg-secondary transition-colors shrink-0"
              >
                <ArrowLeft className="size-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-5">
              {transcriptLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="size-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="prose prose-sm max-w-none dark:prose-invert whitespace-pre-wrap text-[15px] leading-relaxed">
                  {transcriptContent || '暂无转写内容'}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
