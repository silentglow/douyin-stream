import { useEffect, useState, useCallback, useMemo, memo } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import {
  ArrowLeft, RefreshCw, Loader2, FileText, Star, Trash2,
  Download, MoreHorizontal, Eye, EyeOff, X, FolderOpen, ExternalLink,
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useStore } from '@/store/useStore';
import {
  getAssetsByCreator, getAssetTranscript, markAsset, deleteAsset,
  exportTranscripts, triggerCreatorDownload, getAssetFileUrl, browseAssetFolder,
} from '@/lib/api';
import type { FolderBrowseResult } from '@/lib/api';
import { TranscriptReader } from '@/components/ui/TranscriptReader';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Virtuoso } from 'react-virtuoso';
import type { Asset } from '@/types';

function StatusLabel({ status, error }: { status: string; error?: string | null }) {
  if (status === 'completed') {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-patina)] tracking-[0.16em] uppercase">
        <span className="status-dot bg-[var(--color-patina)]" />已转写
      </span>
    );
  }
  if (status === 'failed' || error) {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-iron)] tracking-[0.16em] uppercase max-w-[160px] truncate">
        <span className="status-dot bg-[var(--color-iron)]" />{error ? '失败' : '失败'}
      </span>
    );
  }
  if (status === 'pending' || status === 'queued' || status === 'none' || !status) {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-smoke)] tracking-[0.16em] uppercase">
        <span className="status-dot bg-[var(--color-smoke)]" />待转写
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-rust)] tracking-[0.16em] uppercase">
      <span className="status-dot bg-[var(--color-rust)] pulse-dot" />转写中
    </span>
  );
}

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
  asset, bulkMode, isSelected, onToggleSelect, onViewTranscript, onToggleStar, onOpenMenu,
}: AssetListItemProps) {
  const canView = asset.transcript_status === 'completed' && asset.transcript_path;
  return (
    <div
      className={cn(
        'grid grid-cols-[auto_1fr_auto] items-center gap-4 px-6 py-4 border-b border-[var(--color-hairline-faint)] transition-colors group relative',
        canView || bulkMode ? 'cursor-pointer' : 'cursor-default',
        isSelected ? 'bg-[rgba(198,107,62,0.06)]' : 'hover:bg-[rgba(243,238,219,0.02)]',
        asset.transcript_status === 'failed' && 'before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[2px] before:bg-[var(--color-iron)]'
      )}
      onClick={() => {
        if (bulkMode) onToggleSelect(asset.asset_id);
        else if (canView) onViewTranscript(asset);
      }}
    >
      {/* Checkbox in bulk mode */}
      {bulkMode ? (
        <div className={cn(
          'w-4 h-4 border flex items-center justify-center shrink-0 transition-all',
          isSelected
            ? 'bg-[var(--color-rust)] border-[var(--color-rust)]'
            : 'border-[var(--color-hairline-strong)]'
        )}>
          {isSelected && <div className="w-2 h-2 bg-[var(--color-ink)]" />}
        </div>
      ) : (
        <div className="w-4 flex-shrink-0">
          {!asset.is_read && asset.transcript_status === 'completed' && (
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-rust)] block" />
          )}
        </div>
      )}

      {/* Title + meta */}
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          {asset.is_starred && (
            <Star className="w-3 h-3 text-[var(--color-ember)] fill-[var(--color-ember)] flex-shrink-0 self-center" />
          )}
          <div className={cn(
            'font-display text-[18px] leading-snug line-clamp-1 transition-colors',
            canView
              ? 'text-[var(--color-bone)] group-hover:text-[var(--color-rust)]'
              : 'text-[var(--color-ash)]'
          )}>
            {asset.title || '未命名视频'}
          </div>
        </div>
        <div className="mono-cap mt-1.5 flex items-center gap-2">
          {asset.create_time && (
            <span>{new Date(asset.create_time).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })}</span>
          )}
          {asset.transcript_status === 'running' && asset.transcript_retry_count ? (
            <>
              <span className="text-[var(--color-smoke)]">·</span>
              <span>重试 {asset.transcript_retry_count}</span>
            </>
          ) : null}
        </div>
      </div>

      {/* Status + actions */}
      <div className="flex items-center gap-4 flex-shrink-0">
        <StatusLabel status={asset.transcript_status} error={asset.transcript_last_error} />
        {!bulkMode && (
          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={(e) => onToggleStar(asset, e)}
              className="w-7 h-7 flex items-center justify-center text-[var(--color-ash)] hover:text-[var(--color-ember)] transition-colors"
              title={asset.is_starred ? '取消收藏' : '收藏'}
            >
              <Star className={cn('w-3.5 h-3.5', asset.is_starred && 'fill-[var(--color-ember)] text-[var(--color-ember)]')} strokeWidth={1.5} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onOpenMenu(asset); }}
              className="w-7 h-7 flex items-center justify-center text-[var(--color-ash)] hover:text-[var(--color-rust)] transition-colors"
              title="更多"
            >
              <MoreHorizontal className="w-3.5 h-3.5" strokeWidth={1.5} />
            </button>
          </div>
        )}
      </div>
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
  const [tabFilter, setTabFilter] = useState<'all' | 'completed' | 'starred' | 'failed'>('all');

  const [folderBrowser, setFolderBrowser] = useState<{
    open: boolean; assetId: string; assetTitle: string; data: FolderBrowseResult | null; loading: boolean;
  }>({ open: false, assetId: '', assetTitle: '', data: null, loading: false });

  const isLocal = creatorUid === 'local:upload';
  const creator = creators.find((c) => c.uid === creatorUid);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (viewingAsset) { setViewingAsset(null); }
        else if (actionMenuAsset) setActionMenuAsset(null);
        else if (folderBrowser.open) setFolderBrowser((prev) => ({ ...prev, open: false }));
        else if (bulkMode) { setBulkMode(false); setSelectedAssets(new Set()); }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [viewingAsset, actionMenuAsset, folderBrowser.open, bulkMode]);

  const handleViewTranscript = useCallback(async (asset: Asset) => {
    setViewingAsset(asset);
    setTranscriptLoading(true);
    setTranscriptContent('');
    try {
      const content = await getAssetTranscript(asset.asset_id);
      setTranscriptContent(content);
      if (!asset.is_read) {
        await markAsset(asset.asset_id, { is_read: true });
        setAssets((prev) => prev.map((a) => a.asset_id === asset.asset_id ? { ...a, is_read: true } : a));
      }
    } catch { toast.error('获取转写内容失败'); }
    finally { setTranscriptLoading(false); }
  }, []);

  useEffect(() => {
    if (!creatorUid) return;
    let cancelled = false;
    setLoading(true);
    getAssetsByCreator(decodeURIComponent(creatorUid))
      .then((data) => {
        if (cancelled) return;
        setAssets(data);
        if (openAssetId) {
          const asset = data.find((a) => a.asset_id === openAssetId);
          if (asset && asset.transcript_status === 'completed' && asset.transcript_path) {
            handleViewTranscript(asset);
          }
          navigate(location.pathname, { replace: true, state: {} });
        }
      })
      .catch(() => { if (!cancelled) toast.error('获取素材失败'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [creatorUid]);

  const handleSync = useCallback(async (mode: 'incremental' | 'full' = 'incremental') => {
    if (!creatorUid || syncing) return;
    if (mode === 'full' && !window.confirm('全量重拉将重新下载该创作者的所有视频（包括本地已有的），可能消耗大量网络和磁盘。确定继续？')) {
      return;
    }
    setSyncing(true);
    try {
      await triggerCreatorDownload(decodeURIComponent(creatorUid), mode);
      toast.success(mode === 'full' ? '全量同步任务已派发' : '同步任务已派发');
    } catch { /* api interceptor handles toast */ }
    finally { setSyncing(false); }
  }, [creatorUid, syncing]);

  const handleToggleStar = useCallback(async (asset: Asset, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const newVal = !asset.is_starred;
      await markAsset(asset.asset_id, { is_starred: newVal });
      setAssets((prev) => prev.map((a) => a.asset_id === asset.asset_id ? { ...a, is_starred: newVal } : a));
      toast.success(newVal ? '已收藏' : '已取消收藏');
    } catch { toast.error('操作失败'); }
  }, []);

  const handleToggleRead = useCallback(async (asset: Asset, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const newVal = !asset.is_read;
      await markAsset(asset.asset_id, { is_read: newVal });
      setAssets((prev) => prev.map((a) => a.asset_id === asset.asset_id ? { ...a, is_read: newVal } : a));
    } catch { toast.error('操作失败'); }
  }, []);

  const handleDeleteAsset = useCallback(async (asset: Asset) => {
    if (!confirm(`确定要删除「${asset.title || '未命名视频'}」吗？`)) return;
    try {
      await deleteAsset(asset.asset_id);
      setAssets((prev) => prev.filter((a) => a.asset_id !== asset.asset_id));
      toast.success('已删除');
      setActionMenuAsset(null);
    } catch { toast.error('删除失败'); }
  }, []);

  const handleExportTranscript = useCallback(async (asset: Asset) => {
    if (asset.transcript_status !== 'completed') { toast.error('该素材尚未完成转写'); return; }
    try { await exportTranscripts([asset.asset_id]); toast.success('导出已开始'); setActionMenuAsset(null); }
    catch { toast.error('导出失败'); }
  }, []);

  const handleViewFile = useCallback((asset: Asset) => {
    if (asset.transcript_status !== 'completed') { toast.error('该素材尚未完成转写'); return; }
    const url = getAssetFileUrl(asset.asset_id);
    window.open(url, '_blank');
    setActionMenuAsset(null);
  }, []);

  const handleBrowseFolder = useCallback(async (asset: Asset) => {
    if (!asset.folder_path) { toast.error('该素材没有关联文件夹'); return; }
    setFolderBrowser({ open: true, assetId: asset.asset_id, assetTitle: asset.title || '未命名', data: null, loading: true });
    setActionMenuAsset(null);
    try {
      const data = await browseAssetFolder(asset.asset_id);
      setFolderBrowser((prev) => ({ ...prev, data, loading: false }));
    } catch { toast.error('浏览文件夹失败'); setFolderBrowser((prev) => ({ ...prev, loading: false })); }
  }, []);

  const handleBulkExport = useCallback(async () => {
    const ids = Array.from(selectedAssets).filter((id) => {
      const a = assets.find((x) => x.asset_id === id);
      return a?.transcript_status === 'completed';
    });
    if (ids.length === 0) { toast.error('请选择已完成转写的素材'); return; }
    try { await exportTranscripts(ids); toast.success(`开始导出 ${ids.length} 个转写文件`); setSelectedAssets(new Set()); setBulkMode(false); }
    catch { toast.error('导出失败'); }
  }, [selectedAssets, assets]);

  const handleBulkDelete = useCallback(async () => {
    if (selectedAssets.size === 0) return;
    if (!confirm(`确定要删除 ${selectedAssets.size} 个素材吗？`)) return;
    try {
      const ids = Array.from(selectedAssets);
      for (const id of ids) await deleteAsset(id);
      setAssets((prev) => prev.filter((a) => !selectedAssets.has(a.asset_id)));
      toast.success(`已删除 ${ids.length} 个素材`);
      setSelectedAssets(new Set()); setBulkMode(false);
    } catch { toast.error('删除失败'); }
  }, [selectedAssets]);

  const toggleAssetSelection = useCallback((assetId: string) => {
    setSelectedAssets((prev) => { const next = new Set(prev); if (next.has(assetId)) next.delete(assetId); else next.add(assetId); return next; });
  }, []);

  const filteredAssets = useMemo(() => {
    if (tabFilter === 'all') return assets;
    if (tabFilter === 'completed') return assets.filter((a) => a.transcript_status === 'completed');
    if (tabFilter === 'starred') return assets.filter((a) => a.is_starred);
    if (tabFilter === 'failed') return assets.filter((a) => a.transcript_status === 'failed');
    return assets;
  }, [assets, tabFilter]);

  const completedCount = assets.filter((a) => a.transcript_status === 'completed').length;
  const starredCount = assets.filter((a) => a.is_starred).length;
  const failedCount = assets.filter((a) => a.transcript_status === 'failed').length;

  if (!creator && !isLocal) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-[var(--color-smoke)]">创作者不存在</div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col page-enter">
      {/* ═══ MASTHEAD ═══════════════════════════════════════════ */}
      <header className="px-10 pt-10 pb-8 border-b border-[var(--color-hairline)] flex-shrink-0">
        <button
          onClick={() => navigate('/library')}
          className="flex items-center gap-2 mb-5 text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)] transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" strokeWidth={1.5} />
          返回内容库
        </button>

        <div className="flex items-end justify-between gap-10">
          <div className="flex-1 min-w-0">
            <div className="eyebrow mb-4">
              {assets.length} 个文件
              {completedCount > 0 && <span> · {completedCount} 已转写</span>}
              {starredCount > 0 && <span> · {starredCount} 收藏</span>}
              {failedCount > 0 && <span className="text-[var(--color-iron)]"> · {failedCount} 失败</span>}
            </div>
            <h1 className="font-display text-[clamp(40px,5.5vw,80px)] leading-[0.95] tracking-display text-[var(--color-bone)] truncate">
              {isLocal ? '本地素材' : creator?.nickname ?? '创作者'}
            </h1>
          </div>

          {!isLocal && (
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => handleSync('incremental')}
                disabled={syncing}
                className="btn-sharp flex items-center gap-2"
              >
                {syncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                同步
              </button>
              <button
                onClick={() => handleSync('full')}
                disabled={syncing}
                className="btn-sharp flex items-center gap-2"
                title="全量重拉（忽略本地已有，重新下载所有视频）"
              >
                全量
              </button>
            </div>
          )}
        </div>
      </header>

      {/* ═══ TABS + BULK ════════════════════════════════════════ */}
      <section className="px-10 py-4 border-b border-[var(--color-hairline)] flex-shrink-0 flex items-center justify-between gap-6">
        <div className="flex items-center gap-1">
          {([
            { key: 'all', label: '全部', count: assets.length },
            { key: 'completed', label: '已转写', count: completedCount },
            { key: 'starred', label: '收藏', count: starredCount },
            { key: 'failed', label: '失败', count: failedCount, danger: true },
          ] as const).map((t) => (
            <button
              key={t.key}
              onClick={() => setTabFilter(t.key)}
              className={cn(
                'px-3 py-1.5 text-[12px] font-medium transition-colors border-b',
                tabFilter === t.key
                  ? 'text-[var(--color-rust)] border-[var(--color-rust)]'
                  : 'text-[var(--color-smoke)] hover:text-[var(--color-bone)] border-transparent'
              )}
            >
              {t.label}
              <span className={cn(
                'ml-1.5 font-display text-[14px] tabular',
                'danger' in t && t.danger && t.count > 0 ? 'text-[var(--color-iron)]' : 'text-[var(--color-ash)]'
              )}>
                {t.count}
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          {bulkMode ? (
            <>
              <span className="text-[12px] text-[var(--color-ash)]">已选 <span className="font-display text-[16px] text-[var(--color-rust)] tabular">{selectedAssets.size}</span></span>
              <button
                onClick={handleBulkExport}
                disabled={selectedAssets.size === 0}
                className="btn-sharp disabled:opacity-40 flex items-center gap-2"
              >
                <Download className="w-3.5 h-3.5" />
                导出
              </button>
              <button
                onClick={handleBulkDelete}
                disabled={selectedAssets.size === 0}
                className="btn-sharp border-[var(--color-iron)] text-[var(--color-iron)] hover:bg-[var(--color-iron)] hover:text-[var(--color-ink)] disabled:opacity-40 flex items-center gap-2"
              >
                <Trash2 className="w-3.5 h-3.5" />
                删除
              </button>
              <button
                onClick={() => { setBulkMode(false); setSelectedAssets(new Set()); }}
                className="text-[var(--color-smoke)] hover:text-[var(--color-rust)]"
              >
                <X className="w-4 h-4" />
              </button>
            </>
          ) : assets.length > 0 && (
            <button onClick={() => setBulkMode(true)} className="draw-line text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)]">
              批量操作
            </button>
          )}
        </div>
      </section>

      {/* ═══ LIST ═══════════════════════════════════════════════ */}
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <div>
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-[68px] border-b border-[var(--color-hairline-faint)] skeleton" />
            ))}
          </div>
        ) : filteredAssets.length === 0 ? (
          <div className="py-24 text-center">
            <div className="font-display text-[32px] text-[var(--color-smoke)] mb-2">
              {tabFilter === 'all' ? '还没有素材' : '此筛选下暂无内容'}
            </div>
            <div className="text-[13px] text-[var(--color-ash)]">
              {isLocal ? '在内容库点击「本地上传」添加文件' : '点击上方「同步」按钮获取视频'}
            </div>
          </div>
        ) : (
          <Virtuoso
            data={filteredAssets}
            className="h-full"
            itemContent={(_index, asset) => (
              <AssetListItem
                asset={asset}
                bulkMode={bulkMode}
                isSelected={selectedAssets.has(asset.asset_id)}
                onToggleSelect={toggleAssetSelection}
                onViewTranscript={handleViewTranscript}
                onToggleStar={handleToggleStar}
                onOpenMenu={setActionMenuAsset}
              />
            )}
          />
        )}
      </div>

      {/* ═══ ACTION MENU ════════════════════════════════════════ */}
      <AnimatePresence>
        {actionMenuAsset && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setActionMenuAsset(null)}
          >
            <motion.div
              initial={{ y: '100%', opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: '100%', opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="bg-[var(--color-paper)] w-full sm:max-w-sm sm:mx-4 border border-[var(--color-hairline-strong)] overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-5 border-b border-[var(--color-hairline)]">
                <div className="eyebrow mb-1">素材操作</div>
                <div className="font-display text-[20px] text-[var(--color-bone)] line-clamp-2">{actionMenuAsset.title || '未命名视频'}</div>
              </div>
              <div>
                {actionMenuAsset.transcript_status === 'completed' && (
                  <button onClick={() => handleViewTranscript(actionMenuAsset)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                    <FileText className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                    <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">查看转写</span>
                  </button>
                )}
                <button onClick={(e) => handleToggleRead(actionMenuAsset, e)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                  {actionMenuAsset.is_read ? <EyeOff className="w-3.5 h-3.5 text-[var(--color-ash)]" /> : <Eye className="w-3.5 h-3.5 text-[var(--color-rust)]" />}
                  <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">{actionMenuAsset.is_read ? '标记为未读' : '标记为已读'}</span>
                </button>
                <button onClick={(e) => handleToggleStar(actionMenuAsset, e)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                  <Star className={cn('w-3.5 h-3.5', actionMenuAsset.is_starred ? 'text-[var(--color-ember)] fill-[var(--color-ember)]' : 'text-[var(--color-ash)]')} />
                  <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">{actionMenuAsset.is_starred ? '取消收藏' : '收藏'}</span>
                </button>
                {actionMenuAsset.transcript_status === 'completed' && (
                  <button onClick={() => handleExportTranscript(actionMenuAsset)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                    <Download className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                    <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">导出转写</span>
                  </button>
                )}
                {actionMenuAsset.transcript_status === 'completed' && (
                  <button onClick={() => handleViewFile(actionMenuAsset)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                    <ExternalLink className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                    <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">查看原文件</span>
                  </button>
                )}
                {actionMenuAsset.folder_path && (
                  <button onClick={() => handleBrowseFolder(actionMenuAsset)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                    <FolderOpen className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                    <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">浏览文件夹</span>
                  </button>
                )}
                <button onClick={() => handleDeleteAsset(actionMenuAsset)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(178,89,80,0.08)] transition-colors text-left group">
                  <Trash2 className="w-3.5 h-3.5 text-[var(--color-iron)]" />
                  <span className="text-[14px] text-[var(--color-iron)]">删除素材</span>
                </button>
              </div>
              <div className="p-3 border-t border-[var(--color-hairline)]">
                <button onClick={() => setActionMenuAsset(null)} className="w-full btn-sharp">取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ═══ TRANSCRIPT READER ══════════════════════════════════ */}
      <AnimatePresence>
        {viewingAsset && (
          <TranscriptReader
            asset={viewingAsset}
            content={transcriptContent}
            loading={transcriptLoading}
            onClose={() => setViewingAsset(null)}
            onPrev={() => {
              const completed = assets.filter((a) => a.transcript_status === 'completed');
              const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id);
              if (ci > 0) { setTranscriptContent(''); setTranscriptLoading(true); handleViewTranscript(completed[ci - 1]); }
            }}
            onNext={() => {
              const completed = assets.filter((a) => a.transcript_status === 'completed');
              const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id);
              if (ci >= 0 && ci < completed.length - 1) { setTranscriptContent(''); setTranscriptLoading(true); handleViewTranscript(completed[ci + 1]); }
            }}
            hasPrev={(() => { const completed = assets.filter((a) => a.transcript_status === 'completed'); const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id); return ci > 0; })()}
            hasNext={(() => { const completed = assets.filter((a) => a.transcript_status === 'completed'); const ci = completed.findIndex((a) => a.asset_id === viewingAsset.asset_id); return ci >= 0 && ci < completed.length - 1; })()}
            onAssetUpdate={(updated) => { setAssets((prev) => prev.map((a) => a.asset_id === updated.asset_id ? updated : a)); }}
          />
        )}
      </AnimatePresence>

      {/* ═══ FOLDER BROWSER ═════════════════════════════════════ */}
      <AnimatePresence>
        {folderBrowser.open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setFolderBrowser((prev) => ({ ...prev, open: false }))}
          >
            <motion.div
              initial={{ y: '100%', opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: '100%', opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="bg-[var(--color-paper)] w-full sm:max-w-lg sm:mx-4 border border-[var(--color-hairline-strong)] overflow-hidden max-h-[70vh] flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="p-5 border-b border-[var(--color-hairline)] flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="eyebrow mb-1">关联文件夹</div>
                  <div className="font-display text-[20px] text-[var(--color-bone)] truncate">{folderBrowser.assetTitle}</div>
                  <div className="mono-cap mt-1 truncate">{folderBrowser.data?.path || '加载中...'}</div>
                </div>
                <button onClick={() => setFolderBrowser((prev) => ({ ...prev, open: false }))} className="text-[var(--color-smoke)] hover:text-[var(--color-rust)] flex-shrink-0">
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="overflow-y-auto">
                {folderBrowser.loading && (
                  <div className="py-12 flex items-center justify-center">
                    <Loader2 className="w-4 h-4 text-[var(--color-smoke)] animate-spin" />
                  </div>
                )}
                {!folderBrowser.loading && folderBrowser.data && folderBrowser.data.files.length === 0 && (
                  <div className="py-12 text-center text-[13px] text-[var(--color-ash)]">文件夹为空</div>
                )}
                {!folderBrowser.loading && folderBrowser.data && folderBrowser.data.files.map((file) => (
                  <div key={file.name} className="flex items-center gap-3 px-5 py-3 border-b border-[var(--color-hairline-faint)] last:border-b-0 hover:bg-[rgba(243,238,219,0.025)] transition-colors">
                    <FileText className="w-3.5 h-3.5 text-[var(--color-ash)] shrink-0" strokeWidth={1.5} />
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] truncate text-[var(--color-bone)] font-mono">{file.name}</div>
                      <div className="mono-cap mt-0.5">{(file.size / 1024).toFixed(1)} KB</div>
                    </div>
                    <span className="mono-cap shrink-0 uppercase">{file.suffix.replace('.', '')}</span>
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
