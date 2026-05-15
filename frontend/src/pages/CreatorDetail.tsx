import { useEffect, useState, useCallback, memo } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import {
  ArrowLeft, RefreshCw, Loader2, FileText, Clock, AlertTriangle,
  CheckCircle2, Star, Trash2, Download, MoreHorizontal,
  Eye, EyeOff, X, FolderOpen, ExternalLink
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useStore } from '@/store/useStore';
import {
  getAssetsByCreator, getAssetTranscript, markAsset, deleteAsset,
  exportTranscripts, triggerCreatorDownload, getAssetFileUrl, browseAssetFolder
} from '@/lib/api';
import type { FolderBrowseResult } from '@/lib/api';
import { TranscriptReader } from '@/components/ui/TranscriptReader';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Virtuoso } from 'react-virtuoso';
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
      <span className="inline-flex items-center gap-1 text-small" style={{ color: C.green }}>
        <CheckCircle2 className="size-3" />
        已转写
      </span>
    );
  }
  if (status === 'FAILED' || error) {
    return (
      <span className="inline-flex items-center gap-1 text-small" style={{ color: C.red }}>
        <AlertTriangle className="size-3" />
        失败
      </span>
    );
  }
  if (status === 'PENDING' || status === 'queued') {
    return (
      <span className="inline-flex items-center gap-1 text-small" style={{ color: C.textSecondary }}>
        <Clock className="size-3" />
        待转写
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-small" style={{ color: C.orange }}>
      <Loader2 className="size-3 animate-spin" />
      {status}
    </span>
  );
}

/* ── Virtual list item ── */
interface AssetListItemProps {
  asset: Asset;
  bulkMode: boolean;
  isSelected: boolean;
  onToggleSelect: (id: string) => void;
  onViewTranscript: (asset: Asset) => void;
  onToggleStar: (asset: Asset, e: React.MouseEvent) => void;
  onOpenMenu: (asset: Asset) => void;
}

const AssetListItem = memo(function AssetListItem({
  asset,
  bulkMode,
  isSelected,
  onToggleSelect,
  onViewTranscript,
  onToggleStar,
  onOpenMenu,
}: AssetListItemProps) {
  return (
    <div
      className={cn(
        'bg-card rounded-[18px] apple-shadow-widget p-3.5 flex items-center gap-3 transition-all mx-1',
        bulkMode ? 'cursor-pointer' : 'cursor-pointer active:scale-[0.98]',
        isSelected && 'ring-2 ring-primary/30'
      )}
      onClick={() => {
        if (bulkMode) {
          onToggleSelect(asset.asset_id);
        } else if (asset.transcript_status === 'COMPLETED' && asset.transcript_path) {
          onViewTranscript(asset);
        }
      }}
    >
      {bulkMode && (
        <div className={cn(
          'w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 transition-colors',
          isSelected ? 'bg-primary border-primary' : 'border-muted-foreground/30'
        )}>
          {isSelected && <CheckCircle2 className="size-3.5 text-primary-foreground" />}
        </div>
      )}
      <div className={cn(
        'w-10 h-10 rounded-xl flex items-center justify-center shrink-0',
        asset.transcript_status === 'COMPLETED' ? 'bg-success/10' : 'bg-secondary'
      )}>
        <FileText className="size-5" style={{ color: asset.transcript_status === 'COMPLETED' ? C.green : C.textSecondary }} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate text-foreground">{asset.title || '未命名视频'}</div>
        <div className="flex items-center gap-2 mt-0.5">
          <StatusBadge status={asset.transcript_status} error={asset.transcript_last_error} />
          {!asset.is_read && asset.transcript_status === 'COMPLETED' && (
            <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
          )}
          {asset.is_starred && (
            <Star className="size-3 text-warning fill-warning" />
          )}
          {asset.create_time && (
            <span className="text-small text-muted-foreground">
              {new Date(asset.create_time).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}
            </span>
          )}
        </div>
      </div>
      {!bulkMode && (
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={(e) => onToggleStar(asset, e)}
            className="p-1.5 rounded-lg hover:bg-secondary transition-colors"
            title={asset.is_starred ? '取消收藏' : '收藏'}
          >
            <Star className={cn('size-4', asset.is_starred ? 'text-warning fill-warning' : 'text-muted-foreground')} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onOpenMenu(asset); }}
            className="p-1.5 rounded-lg hover:bg-secondary transition-colors"
          >
            <MoreHorizontal className="size-4 text-muted-foreground" />
          </button>
        </div>
      )}
    </div>
  );
});

export default function CreatorDetail() {
  const { creatorUid } = useParams<{ creatorUid: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const creators = useStore((s) => s.creators);
  const openAssetId = (location.state as { openAssetId?: string } | null)?.openAssetId;

  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [viewingAsset, setViewingAsset] = useState<Asset | null>(null);
  const [transcriptContent, setTranscriptContent] = useState('');
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [selectedAssets, setSelectedAssets] = useState<Set<string>>(new Set());
  const [actionMenuAsset, setActionMenuAsset] = useState<Asset | null>(null);
  const [bulkMode, setBulkMode] = useState(false);

  // Folder browser state
  const [folderBrowser, setFolderBrowser] = useState<{
    open: boolean;
    assetId: string;
    assetTitle: string;
    data: FolderBrowseResult | null;
    loading: boolean;
  }>({ open: false, assetId: '', assetTitle: '', data: null, loading: false });

  const isLocal = creatorUid === 'local:upload';
  const creator = creators.find((c) => c.uid === creatorUid);

  /* Global keyboard shortcuts */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (viewingAsset) {
          e.preventDefault();
          setViewingAsset(null);
        } else if (actionMenuAsset) {
          e.preventDefault();
          setActionMenuAsset(null);
        } else if (folderBrowser.open) {
          e.preventDefault();
          setFolderBrowser((prev) => ({ ...prev, open: false }));
        } else if (bulkMode) {
          e.preventDefault();
          setBulkMode(false);
          setSelectedAssets(new Set());
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [viewingAsset, actionMenuAsset, folderBrowser.open, bulkMode]);

  useEffect(() => {
    if (!creatorUid) return;
    let cancelled = false;
    setLoading(true);
    getAssetsByCreator(decodeURIComponent(creatorUid))
      .then((data) => {
        if (cancelled) return;
        setAssets(data);
        // Auto-open asset from search navigation
        if (openAssetId) {
          const asset = data.find((a) => a.asset_id === openAssetId);
          if (asset && asset.transcript_status === 'COMPLETED' && asset.transcript_path) {
            handleViewTranscript(asset);
          }
          // Clear the state so refresh doesn't re-open
          navigate(location.pathname, { replace: true, state: {} });
        }
      })
      .catch(() => { if (!cancelled) toast.error('获取素材失败'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
      // Mark as read when viewing
      if (!asset.is_read) {
        await markAsset(asset.asset_id, { is_read: true });
        setAssets((prev) => prev.map((a) =>
          a.asset_id === asset.asset_id ? { ...a, is_read: true } : a
        ));
      }
    } catch {
      toast.error('获取转写内容失败');
    } finally {
      setTranscriptLoading(false);
    }
  }, []);

  const handleToggleStar = useCallback(async (asset: Asset, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const newVal = !asset.is_starred;
      await markAsset(asset.asset_id, { is_starred: newVal });
      setAssets((prev) => prev.map((a) =>
        a.asset_id === asset.asset_id ? { ...a, is_starred: newVal } : a
      ));
      toast.success(newVal ? '已收藏' : '已取消收藏');
    } catch {
      toast.error('操作失败');
    }
  }, []);

  const handleToggleRead = useCallback(async (asset: Asset, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const newVal = !asset.is_read;
      await markAsset(asset.asset_id, { is_read: newVal });
      setAssets((prev) => prev.map((a) =>
        a.asset_id === asset.asset_id ? { ...a, is_read: newVal } : a
      ));
    } catch {
      toast.error('操作失败');
    }
  }, []);

  const handleDeleteAsset = useCallback(async (asset: Asset) => {
    if (!confirm(`确定要删除「${asset.title || '未命名视频'}」吗？`)) return;
    try {
      await deleteAsset(asset.asset_id);
      setAssets((prev) => prev.filter((a) => a.asset_id !== asset.asset_id));
      toast.success('已删除');
      setActionMenuAsset(null);
    } catch {
      toast.error('删除失败');
    }
  }, []);

  const handleExportTranscript = useCallback(async (asset: Asset) => {
    if (asset.transcript_status !== 'COMPLETED') {
      toast.error('该素材尚未完成转写');
      return;
    }
    try {
      await exportTranscripts([asset.asset_id]);
      toast.success('导出已开始');
      setActionMenuAsset(null);
    } catch {
      toast.error('导出失败');
    }
  }, []);

  const handleViewFile = useCallback((asset: Asset) => {
    if (asset.transcript_status !== 'COMPLETED') {
      toast.error('该素材尚未完成转写');
      return;
    }
    const url = getAssetFileUrl(asset.asset_id);
    window.open(url, '_blank');
    setActionMenuAsset(null);
  }, []);

  const handleBrowseFolder = useCallback(async (asset: Asset) => {
    if (!asset.folder_path) {
      toast.error('该素材没有关联文件夹');
      return;
    }
    setFolderBrowser({
      open: true,
      assetId: asset.asset_id,
      assetTitle: asset.title || '未命名',
      data: null,
      loading: true,
    });
    setActionMenuAsset(null);
    try {
      const data = await browseAssetFolder(asset.asset_id);
      setFolderBrowser((prev) => ({ ...prev, data, loading: false }));
    } catch {
      toast.error('浏览文件夹失败');
      setFolderBrowser((prev) => ({ ...prev, loading: false }));
    }
  }, []);

  const handleBulkExport = useCallback(async () => {
    const ids = Array.from(selectedAssets).filter((id) => {
      const a = assets.find((x) => x.asset_id === id);
      return a?.transcript_status === 'COMPLETED';
    });
    if (ids.length === 0) {
      toast.error('请选择已完成转写的素材');
      return;
    }
    try {
      await exportTranscripts(ids);
      toast.success(`开始导出 ${ids.length} 个转写文件`);
      setSelectedAssets(new Set());
      setBulkMode(false);
    } catch {
      toast.error('导出失败');
    }
  }, [selectedAssets, assets]);

  const handleBulkDelete = useCallback(async () => {
    if (selectedAssets.size === 0) return;
    if (!confirm(`确定要删除 ${selectedAssets.size} 个素材吗？`)) return;
    try {
      const ids = Array.from(selectedAssets);
      for (const id of ids) {
        await deleteAsset(id);
      }
      setAssets((prev) => prev.filter((a) => !selectedAssets.has(a.asset_id)));
      toast.success(`已删除 ${ids.length} 个素材`);
      setSelectedAssets(new Set());
      setBulkMode(false);
    } catch {
      toast.error('删除失败');
    }
  }, [selectedAssets]);

  const toggleAssetSelection = useCallback((assetId: string) => {
    setSelectedAssets((prev) => {
      const next = new Set(prev);
      if (next.has(assetId)) next.delete(assetId);
      else next.add(assetId);
      return next;
    });
  }, []);

  if (!creator && !isLocal) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-muted-foreground">创作者不存在</div>
      </div>
    );
  }

  const completedCount = assets.filter((a) => a.transcript_status === 'COMPLETED').length;
  const starredCount = assets.filter((a) => a.is_starred).length;

  return (
    <div className="h-full p-7 px-8 max-sm:p-4 max-sm:pb-20 flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/library')}
          className="flex items-center justify-center w-9 h-9 rounded-xl bg-secondary hover:bg-secondary/80 transition-colors"
        >
          <ArrowLeft className="size-[18px] text-muted-foreground" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="text-title-1 font-bold tracking-tight truncate">{isLocal ? '本地素材' : creator?.nickname ?? '创作者'}</div>
          <div className="text-caption text-muted-foreground">
            {assets.length} 个文件 · {completedCount} 个已转写{starredCount > 0 ? ` · ${starredCount} 个收藏` : ''}
          </div>
        </div>
        {!isLocal && (
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary/90 transition-all active:scale-[0.97] disabled:opacity-50"
          >
            {syncing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            同步
          </button>
        )}
      </div>

      {/* Bulk action bar */}
      {bulkMode && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2 mb-4 p-3 bg-card rounded-[18px] apple-shadow-widget"
        >
          <span className="text-sm text-muted-foreground flex-1">已选择 {selectedAssets.size} 项</span>
          <button
            onClick={handleBulkExport}
            disabled={selectedAssets.size === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary rounded-lg text-sm font-medium hover:bg-primary hover:text-primary-foreground transition-all disabled:opacity-50"
          >
            <Download className="size-3.5" />
            导出转写
          </button>
          <button
            onClick={handleBulkDelete}
            disabled={selectedAssets.size === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary rounded-lg text-sm font-medium hover:bg-destructive hover:text-destructive-foreground transition-all disabled:opacity-50"
          >
            <Trash2 className="size-3.5" />
            删除
          </button>
          <button
            onClick={() => { setBulkMode(false); setSelectedAssets(new Set()); }}
            className="p-1.5 rounded-lg hover:bg-secondary transition-colors"
          >
            <X className="size-4 text-muted-foreground" />
          </button>
        </motion.div>
      )}

      {!bulkMode && assets.length > 0 && (
        <div className="flex items-center gap-2 mb-4">
          <button
            onClick={() => setBulkMode(true)}
            className="text-sm text-primary font-medium hover:underline"
          >
            批量操作
          </button>
        </div>
      )}

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
          <div className="text-xl font-semibold text-muted-foreground">还没有素材</div>
          <div className="text-caption text-muted-foreground mt-1">{isLocal ? '在 Library 页面点击「本地转写」添加文件' : '点击上方「同步」按钮获取视频'}</div>
        </div>
      ) : (
        <div className="flex-1 overflow-hidden -mx-1">
          <Virtuoso
            data={assets}
            itemContent={(_index, asset) => (
              <div className="py-1">
                <AssetListItem
                  asset={asset}
                  bulkMode={bulkMode}
                  isSelected={selectedAssets.has(asset.asset_id)}
                  onToggleSelect={toggleAssetSelection}
                  onViewTranscript={handleViewTranscript}
                  onToggleStar={handleToggleStar}
                  onOpenMenu={setActionMenuAsset}
                />
              </div>
            )}
          />
        </div>
      )}

      {/* Action Menu Modal */}
      <AnimatePresence>
        {actionMenuAsset && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm"
            onClick={() => setActionMenuAsset(null)}
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
                <div className="text-sm font-semibold truncate">{actionMenuAsset.title || '未命名视频'}</div>
              </div>
              <div className="p-2">
                {actionMenuAsset.transcript_status === 'COMPLETED' && (
                  <button
                    onClick={() => handleViewTranscript(actionMenuAsset)}
                    className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-secondary transition-colors text-left"
                  >
                    <FileText className="size-4 text-primary" />
                    <span className="text-sm">查看转写</span>
                  </button>
                )}
                <button
                  onClick={() => handleToggleRead(actionMenuAsset, { stopPropagation: () => {} } as React.MouseEvent)}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-secondary transition-colors text-left"
                >
                  {actionMenuAsset.is_read ? <EyeOff className="size-4 text-muted-foreground" /> : <Eye className="size-4 text-primary" />}
                  <span className="text-sm">{actionMenuAsset.is_read ? '标记为未读' : '标记为已读'}</span>
                </button>
                <button
                  onClick={() => handleToggleStar(actionMenuAsset, { stopPropagation: () => {} } as React.MouseEvent)}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-secondary transition-colors text-left"
                >
                  <Star className={cn('size-4', actionMenuAsset.is_starred ? 'text-warning fill-warning' : 'text-muted-foreground')} />
                  <span className="text-sm">{actionMenuAsset.is_starred ? '取消收藏' : '收藏'}</span>
                </button>
                {actionMenuAsset.transcript_status === 'COMPLETED' && (
                  <button
                    onClick={() => handleExportTranscript(actionMenuAsset)}
                    className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-secondary transition-colors text-left"
                  >
                    <Download className="size-4 text-primary" />
                    <span className="text-sm">导出转写</span>
                  </button>
                )}
                {actionMenuAsset.transcript_status === 'COMPLETED' && (
                  <button
                    onClick={() => handleViewFile(actionMenuAsset)}
                    className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-secondary transition-colors text-left"
                  >
                    <ExternalLink className="size-4 text-primary" />
                    <span className="text-sm">查看原文件</span>
                  </button>
                )}
                {actionMenuAsset.folder_path && (
                  <button
                    onClick={() => handleBrowseFolder(actionMenuAsset)}
                    className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-secondary transition-colors text-left"
                  >
                    <FolderOpen className="size-4 text-primary" />
                    <span className="text-sm">浏览文件夹</span>
                  </button>
                )}
                <div className="h-px bg-border/40 my-1" />
                <button
                  onClick={() => handleDeleteAsset(actionMenuAsset)}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-destructive/10 transition-colors text-left"
                >
                  <Trash2 className="size-4 text-destructive" />
                  <span className="text-sm text-destructive">删除素材</span>
                </button>
              </div>
              <div className="p-2 border-t border-border/40">
                <button
                  onClick={() => setActionMenuAsset(null)}
                  className="w-full py-3 rounded-xl bg-secondary text-sm font-medium hover:bg-secondary/80 transition-colors"
                >
                  取消
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Transcript Reader */}
      <AnimatePresence>
        {viewingAsset && (
          <TranscriptReader
            asset={viewingAsset}
            content={transcriptContent}
            loading={transcriptLoading}
            onClose={() => setViewingAsset(null)}
            onPrev={() => {
              const completed = assets.filter((a) => a.transcript_status === 'COMPLETED');
              const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id);
              if (ci > 0) {
                setTranscriptContent('');
                setTranscriptLoading(true);
                handleViewTranscript(completed[ci - 1]);
              }
            }}
            onNext={() => {
              const completed = assets.filter((a) => a.transcript_status === 'COMPLETED');
              const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id);
              if (ci >= 0 && ci < completed.length - 1) {
                setTranscriptContent('');
                setTranscriptLoading(true);
                handleViewTranscript(completed[ci + 1]);
              }
            }}
            hasPrev={(() => {
              const completed = assets.filter((a) => a.transcript_status === 'COMPLETED');
              const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id);
              return ci > 0;
            })()}
            hasNext={(() => {
              const completed = assets.filter((a) => a.transcript_status === 'COMPLETED');
              const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id);
              return ci >= 0 && ci < completed.length - 1;
            })()}
            onAssetUpdate={(updated) => {
              setAssets((prev) => prev.map((a) => a.asset_id === updated.asset_id ? updated : a));
            }}
          />
        )}
      </AnimatePresence>

      {/* Folder Browser */}
      <AnimatePresence>
        {folderBrowser.open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 backdrop-blur-sm"
            onClick={() => setFolderBrowser((prev) => ({ ...prev, open: false }))}
          >
            <motion.div
              initial={{ y: '100%', opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: '100%', opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="bg-card rounded-t-[22px] sm:rounded-[22px] w-full sm:w-full sm:max-w-lg sm:mx-4 shadow-xl overflow-hidden max-h-[70vh] flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-4 border-b border-border/40 flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold truncate">{folderBrowser.assetTitle}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {folderBrowser.data?.path || '加载中...'}
                  </div>
                </div>
                <button
                  onClick={() => setFolderBrowser((prev) => ({ ...prev, open: false }))}
                  className="p-1.5 rounded-lg hover:bg-secondary transition-colors"
                >
                  <X className="size-4 text-muted-foreground" />
                </button>
              </div>
              <div className="overflow-y-auto p-2">
                {folderBrowser.loading && (
                  <div className="py-8 flex items-center justify-center">
                    <Loader2 className="size-5 text-muted-foreground animate-spin" />
                  </div>
                )}
                {!folderBrowser.loading && folderBrowser.data && folderBrowser.data.files.length === 0 && (
                  <div className="py-8 text-center text-sm text-muted-foreground">文件夹为空</div>
                )}
                {!folderBrowser.loading && folderBrowser.data && folderBrowser.data.files.map((file) => (
                  <div
                    key={file.name}
                    className="flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-secondary transition-colors"
                  >
                    <FileText className="size-4 text-primary shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{file.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {(file.size / 1024).toFixed(1)} KB
                      </div>
                    </div>
                    <span className="text-xs text-muted-foreground uppercase shrink-0">
                      {file.suffix.replace('.', '')}
                    </span>
                  </div>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
