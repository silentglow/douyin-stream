import { useMemo, useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '@/store/useStore';
import {
  addCreator, deleteCreator, triggerCreatorDownload, toggleCreatorAutoSync, getAssetsByCreator, bulkDeleteAssets,
} from '@/lib/api';
import { selectFolder, scanDirectory, triggerLocalTranscribe } from '@/lib/api';
import { toast } from 'sonner';

type FilterType = 'all' | 'video' | 'transcript';

export function useLibraryDetail() {
  const navigate = useNavigate();
  const allCreators = useStore((state) => state.creators);
  const storeFetchCreators = useStore((state) => state.fetchCreators);

  const creators = useMemo(
    () => allCreators.filter((c) => c.platform !== 'local' && !c.uid.startsWith('local:')),
    [allCreators]
  );

  const hasLocalAssets = allCreators.some((c) => c.uid === 'local:upload');
  const localAssetCount = allCreators.find((c) => c.uid === 'local:upload')?.asset_count || 0;

  const [filter, setFilter] = useState<FilterType>('all');
  const [search, setSearch] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [actionMenuCreator, setActionMenuCreator] = useState<{ uid: string; nickname: string } | null>(null);

  const [localTranscribeOpen, setLocalTranscribeOpen] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scannedFiles, setScannedFiles] = useState<Array<{ path: string; name: string }>>([]);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [transcribing, setTranscribing] = useState(false);
  const [scannedDirectory, setScannedDirectory] = useState('');
  const [deleteAfter, setDeleteAfter] = useState(false);

  const [deleteConfirm, setDeleteConfirm] = useState<{
    uid: string;
    nickname: string;
    assetCount: number;
    deleteAssets: boolean;
  } | null>(null);

  useEffect(() => { storeFetchCreators().then(() => setLoading(false)); }, [storeFetchCreators]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (actionMenuCreator) setActionMenuCreator(null);
        else if (localTranscribeOpen) {
          setLocalTranscribeOpen(false);
          setScannedFiles([]);
          setSelectedFiles(new Set());
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [actionMenuCreator, localTranscribeOpen]);

  const filteredCreators = useMemo(() => {
    let result = creators;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter((c) =>
        c.nickname?.toLowerCase().includes(q) || c.uid?.toLowerCase().includes(q)
      );
    }
    if (filter === 'video') result = result.filter((c) => (c.asset_count || 0) > 0);
    else if (filter === 'transcript') result = result.filter((c) => (c.transcript_completed_count || 0) > 0);
    return result;
  }, [creators, search, filter]);

  const handleAddCreator = useCallback(async () => {
    if (!newUrl.trim()) return;
    setIsAdding(true);
    try {
      await addCreator(newUrl.trim());
      toast.success('创作者已收录');
      setNewUrl('');
      await storeFetchCreators(true);
    } catch { /* api interceptor handles toast */ }
    finally { setIsAdding(false); }
  }, [newUrl, storeFetchCreators]);

  const handleSync = useCallback(async (uid: string, e: { stopPropagation: () => void } | React.MouseEvent, mode: 'incremental' | 'full' = 'incremental') => {
    e.stopPropagation();
    if (syncingIds.has(uid)) return;
    if (mode === 'full' && !window.confirm('全量重拉将重新下载该创作者的所有视频（包括本地已有的），可能消耗大量网络和磁盘。确定继续？')) {
      return;
    }
    setSyncingIds((prev) => new Set(prev).add(uid));
    try {
      await triggerCreatorDownload(uid, mode);
      toast.success(mode === 'full' ? '全量同步任务已派发' : '同步任务已派发');
    } catch { /* api interceptor handles toast */ }
    finally {
      setSyncingIds((prev) => { const next = new Set(prev); next.delete(uid); return next; });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDeleteCreator = useCallback((uid: string) => {
    const creator = allCreators.find((c) => c.uid === uid);
    if (!creator) return;
    setDeleteConfirm({ uid, nickname: creator.nickname || '创作者', assetCount: creator.asset_count || 0, deleteAssets: false });
    setActionMenuCreator(null);
  }, [allCreators]);

  const executeDeleteCreator = useCallback(async () => {
    if (!deleteConfirm) return;
    const { uid, deleteAssets, assetCount } = deleteConfirm;
    setDeletingIds((prev) => new Set(prev).add(uid));
    try {
      if (deleteAssets && assetCount > 0) {
        const assets = await getAssetsByCreator(uid);
        if (assets.length > 0) await bulkDeleteAssets(assets.map((a) => a.asset_id));
      }
      await deleteCreator(uid);
      toast.success(deleteAssets ? '已删除创作者及素材' : '已删除创作者');
      await storeFetchCreators(true);
    } catch {
      toast.error('删除失败');
    } finally {
      setDeletingIds((prev) => { const next = new Set(prev); next.delete(uid); return next; });
      setDeleteConfirm(null);
    }
  }, [deleteConfirm, storeFetchCreators]);

  const handleToggleAutoSync = useCallback(async (uid: string) => {
    const creator = creators.find((c) => c.uid === uid);
    if (!creator) return;
    const newValue = !creator.auto_sync;
    try {
      await toggleCreatorAutoSync(uid, newValue);
      useStore.setState((state) => ({
        creators: state.creators.map((c) => c.uid === uid ? { ...c, auto_sync: newValue } : c),
      }));
      toast.success(newValue ? '已开启自动同步' : '已关闭自动同步');
    } catch { /* api interceptor handles toast */ }
  }, [creators]);

  const handleSelectFolder = useCallback(async () => {
    setScanning(true);
    try {
      const { directory } = await selectFolder();
      const { files } = await scanDirectory(directory);
      setScannedDirectory(directory);
      setScannedFiles(files.map((f: { path: string; name: string }) => ({ path: f.path, name: f.name })));
      setSelectedFiles(new Set(files.map((f: { path: string; name: string }) => f.path)));
      setLocalTranscribeOpen(true);
    } catch { /* api interceptor handles toast */ }
    finally { setScanning(false); }
  }, []);

  const toggleFileSelection = useCallback((path: string) => {
    setSelectedFiles((prev) => { const next = new Set(prev); if (next.has(path)) next.delete(path); else next.add(path); return next; });
  }, []);

  const handleStartLocalTranscribe = useCallback(async () => {
    if (selectedFiles.size === 0) return;
    setTranscribing(true);
    try {
      const paths = Array.from(selectedFiles);
      await triggerLocalTranscribe(paths, deleteAfter, scannedDirectory);
      toast.success(`已提交 ${paths.length} 个文件的转写任务`);
      setLocalTranscribeOpen(false);
      setScannedFiles([]);
      setSelectedFiles(new Set());
      setScannedDirectory('');
      setDeleteAfter(false);
    } catch { /* api interceptor handles toast */ }
    finally { setTranscribing(false); }
  }, [selectedFiles, scannedDirectory, deleteAfter]);

  const totalAssets = creators.reduce((s, c) => s + (c.asset_count || 0), 0);
  const totalTranscribed = creators.reduce((s, c) => s + (c.transcript_completed_count || 0), 0);
  const autoCount = creators.filter(c => c.auto_sync).length;

  return {
    navigate,
    allCreators,
    creators,
    hasLocalAssets,
    localAssetCount,
    filter,
    setFilter,
    search,
    setSearch,
    newUrl,
    setNewUrl,
    isAdding,
    loading,
    syncingIds,
    deletingIds,
    actionMenuCreator,
    setActionMenuCreator,
    localTranscribeOpen,
    setLocalTranscribeOpen,
    scanning,
    scannedFiles,
    setScannedFiles,
    selectedFiles,
    setSelectedFiles,
    transcribing,
    scannedDirectory,
    deleteConfirm,
    setDeleteConfirm,
    filteredCreators,
    handleAddCreator,
    handleSync,
    handleDeleteCreator,
    executeDeleteCreator,
    handleToggleAutoSync,
    handleSelectFolder,
    toggleFileSelection,
    handleStartLocalTranscribe,
    deleteAfter,
    toggleDeleteAfter: () => setDeleteAfter((prev) => !prev),
    totalAssets,
    totalTranscribed,
    autoCount,
  };
}
