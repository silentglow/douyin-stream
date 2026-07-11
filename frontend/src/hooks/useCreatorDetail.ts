import { useEffect, useState, useCallback, useMemo } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useStore } from '@/store/useStore';
import {
  getAssetsByCreator, getAssetTranscript, markAsset, deleteAsset, bulkDeleteAssets, bulkMarkAssets,
  exportTranscripts, triggerCreatorDownload, getAssetFileUrl, browseAssetFolder,
} from '@/lib/api';
import type { FolderBrowseResult } from '@/lib/api';
import type { Asset } from '@/types';
import { toast } from 'sonner';
import { FULL_SYNC_CONFIRM } from '@/lib/format';

export function useCreatorDetail() {
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
    } catch (err: unknown) {
      setViewingAsset(null);
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        toast.error('文稿文件不在本地', {
          description: '可能已外置归档。数据库记录仍在；增量同步不会因此重下。若需阅读请把文件放回原路径，或从归档位置打开。',
        });
      } else {
        toast.error('获取转写内容失败');
      }
    }
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
    if (mode === 'full' && !window.confirm(FULL_SYNC_CONFIRM)) return;
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
      await bulkDeleteAssets(ids);
      setAssets((prev) => prev.filter((a) => !selectedAssets.has(a.asset_id)));
      toast.success(`已删除 ${ids.length} 个素材`);
      setSelectedAssets(new Set()); setBulkMode(false);
    } catch { toast.error('删除失败'); }
  }, [selectedAssets]);

  const handleBulkMarkRead = useCallback(async () => {
    if (selectedAssets.size === 0) return;
    try {
      const ids = Array.from(selectedAssets);
      await bulkMarkAssets(ids, { is_read: true });
      setAssets((prev) => prev.map((a) => selectedAssets.has(a.asset_id) ? { ...a, is_read: true } : a));
      toast.success(`已标记 ${ids.length} 个素材为已读`);
      setSelectedAssets(new Set()); setBulkMode(false);
    } catch { toast.error('标记失败'); }
  }, [selectedAssets]);

  const handleBulkMarkStar = useCallback(async () => {
    if (selectedAssets.size === 0) return;
    try {
      const ids = Array.from(selectedAssets);
      await bulkMarkAssets(ids, { is_starred: true });
      setAssets((prev) => prev.map((a) => selectedAssets.has(a.asset_id) ? { ...a, is_starred: true } : a));
      toast.success(`已收藏 ${ids.length} 个素材`);
      setSelectedAssets(new Set()); setBulkMode(false);
    } catch { toast.error('收藏失败'); }
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

  return {
    creatorUid,
    navigate,
    assets,
    setAssets,
    loading,
    syncing,
    viewingAsset,
    setViewingAsset,
    transcriptContent,
    setTranscriptContent,
    transcriptLoading,
    setTranscriptLoading,
    selectedAssets,
    setSelectedAssets,
    actionMenuAsset,
    setActionMenuAsset,
    bulkMode,
    setBulkMode,
    tabFilter,
    setTabFilter,
    folderBrowser,
    setFolderBrowser,
    isLocal,
    creator,
    handleViewTranscript,
    handleSync,
    handleToggleStar,
    handleToggleRead,
    handleDeleteAsset,
    handleExportTranscript,
    handleViewFile,
    handleBrowseFolder,
    handleBulkExport,
    handleBulkDelete,
    handleBulkMarkRead,
    handleBulkMarkStar,
    toggleAssetSelection,
    filteredAssets,
    completedCount,
    starredCount,
    failedCount,
  };
}
