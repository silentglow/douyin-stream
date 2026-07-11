import { useMemo, useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '@/store/useStore';
import {
  addCreator, deleteCreator, triggerCreatorDownload, toggleCreatorAutoSync, bulkSetCreatorAutoSync, refollowCreator,
} from '@/lib/api';
import { selectFolder, scanDirectory, triggerLocalTranscribe } from '@/lib/api';
import { toast } from 'sonner';
import { FULL_SYNC_CONFIRM } from '@/lib/format';
import type { RemoveMode, RemoveTarget } from '@/components/library/DeleteConfirmModal';

type FilterType = 'all' | 'video' | 'transcript' | 'auto' | 'manual' | 'following' | 'unfollowed';

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
  const [deleteAfter, setDeleteAfter] = useState(true);

  const [selectedUids, setSelectedUids] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [removeDialog, setRemoveDialog] = useState<{
    targets: RemoveTarget[];
    mode: RemoveMode;
  } | null>(null);

  useEffect(() => { storeFetchCreators().then(() => setLoading(false)); }, [storeFetchCreators]);

  // Drop selection for creators no longer in filtered list? Keep across filter — better clear uids not in allCreators
  useEffect(() => {
    const valid = new Set(creators.map((c) => c.uid));
    setSelectedUids((prev) => {
      const next = new Set([...prev].filter((id) => valid.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [creators]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (removeDialog) setRemoveDialog(null);
        else if (actionMenuCreator) setActionMenuCreator(null);
        else if (selectedUids.size > 0) setSelectedUids(new Set());
        else if (localTranscribeOpen) {
          setLocalTranscribeOpen(false);
          setScannedFiles([]);
          setSelectedFiles(new Set());
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [actionMenuCreator, localTranscribeOpen, selectedUids.size, removeDialog]);

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
    else if (filter === 'auto') result = result.filter((c) => !!c.auto_sync && c.sync_status !== 'unfollowed');
    else if (filter === 'manual') result = result.filter((c) => !c.auto_sync && c.sync_status !== 'unfollowed');
    else if (filter === 'following') result = result.filter((c) => c.sync_status !== 'unfollowed');
    else if (filter === 'unfollowed') result = result.filter((c) => c.sync_status === 'unfollowed');
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
    if (mode === 'full' && !window.confirm(FULL_SYNC_CONFIRM)) {
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
  }, [syncingIds]);

  const toRemoveTarget = useCallback((uid: string): RemoveTarget | null => {
    const creator = allCreators.find((c) => c.uid === uid);
    if (!creator) return null;
    return {
      uid,
      nickname: creator.nickname || '创作者',
      assetCount: creator.asset_count || 0,
      transcriptCount: creator.transcript_completed_count || 0,
    };
  }, [allCreators]);

  const handleDeleteCreator = useCallback((uid: string) => {
    const target = toRemoveTarget(uid);
    if (!target) return;
    const creator = allCreators.find((c) => c.uid === uid);
    setRemoveDialog({
      targets: [target],
      mode: creator?.sync_status === 'unfollowed' ? 'purge' : 'keep_content',
    });
    setActionMenuCreator(null);
  }, [allCreators, toRemoveTarget]);

  const openBulkRemove = useCallback((mode: RemoveMode = 'keep_content') => {
    const targets = [...selectedUids]
      .map((uid) => toRemoveTarget(uid))
      .filter((t): t is RemoveTarget => !!t);
    if (targets.length === 0) {
      toast.error('请先勾选创作者');
      return;
    }
    setRemoveDialog({ targets, mode });
  }, [selectedUids, toRemoveTarget]);

  const executeRemove = useCallback(async () => {
    if (!removeDialog) return;
    const { targets, mode } = removeDialog;
    const keepContent = mode === 'keep_content';
    const uids = targets.map((t) => t.uid);
    setBulkBusy(true);
    setDeletingIds((prev) => {
      const next = new Set(prev);
      uids.forEach((id) => next.add(id));
      return next;
    });
    let ok = 0;
    let fail = 0;
    try {
      for (const uid of uids) {
        try {
          await deleteCreator(uid, { keepContent });
          ok += 1;
        } catch {
          fail += 1;
        }
      }
      if (keepContent) {
        useStore.setState((state) => ({
          creators: state.creators.map((c) =>
            uids.includes(c.uid) ? { ...c, auto_sync: 0, sync_status: 'unfollowed' } : c,
          ),
        }));
        toast.success(
          uids.length === 1 ? '已停跟，文稿仍保留' : `已停跟 ${ok} 位创作者`,
          {
            description: fail
              ? `${fail} 位失败`
              : '可在筛选「已停跟」中找到',
          },
        );
      } else {
        useStore.setState((state) => ({
          creators: state.creators.filter((c) => !uids.includes(c.uid)),
        }));
        toast.success(
          uids.length === 1 ? '已彻底删除' : `已删除 ${ok} 位创作者`,
          fail ? { description: `${fail} 位失败` } : undefined,
        );
      }
      setSelectedUids(new Set());
      await storeFetchCreators(true);
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        uids.forEach((id) => next.delete(id));
        return next;
      });
      setBulkBusy(false);
      setRemoveDialog(null);
    }
  }, [removeDialog, storeFetchCreators]);

  const toggleSelectUid = useCallback((uid: string) => {
    setSelectedUids((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });
  }, []);

  const selectAllFiltered = useCallback(() => {
    setSelectedUids(new Set(filteredCreators.map((c) => c.uid)));
  }, [filteredCreators]);

  const clearSelection = useCallback(() => setSelectedUids(new Set()), []);

  const toggleSelectAllFiltered = useCallback(() => {
    const ids = filteredCreators.map((c) => c.uid);
    if (ids.length === 0) return;
    const allSelected = ids.every((id) => selectedUids.has(id));
    if (allSelected) {
      setSelectedUids((prev) => {
        const next = new Set(prev);
        ids.forEach((id) => next.delete(id));
        return next;
      });
    } else {
      setSelectedUids((prev) => {
        const next = new Set(prev);
        ids.forEach((id) => next.add(id));
        return next;
      });
    }
  }, [filteredCreators, selectedUids]);

  const handleBulkSetAutoOnSelection = useCallback(async (enable: boolean) => {
    const uids = [...selectedUids];
    if (uids.length === 0) return;
    setBulkBusy(true);
    let ok = 0;
    try {
      for (const uid of uids) {
        try {
          await toggleCreatorAutoSync(uid, enable);
          ok += 1;
        } catch { /* continue */ }
      }
      useStore.setState((state) => ({
        creators: state.creators.map((c) =>
          uids.includes(c.uid) ? { ...c, auto_sync: enable ? 1 : 0 } : c,
        ),
      }));
      toast.success(enable ? `已为 ${ok} 人开启自动跟进` : `已为 ${ok} 人关闭自动跟进`);
      await storeFetchCreators(true);
    } finally {
      setBulkBusy(false);
    }
  }, [selectedUids, storeFetchCreators]);

  const handleBulkSyncSelection = useCallback(async () => {
    const uids = [...selectedUids];
    if (uids.length === 0) return;
    if (!window.confirm(`对选中的 ${uids.length} 位创作者发起增量同步？`)) return;
    setBulkBusy(true);
    let ok = 0;
    try {
      for (const uid of uids) {
        try {
          await triggerCreatorDownload(uid, 'incremental');
          ok += 1;
        } catch { /* continue */ }
      }
      toast.success(`已派发 ${ok} 个同步任务`);
    } finally {
      setBulkBusy(false);
    }
  }, [selectedUids]);

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

  const handleRefollow = useCallback(async (uid: string) => {
    try {
      await refollowCreator(uid);
      useStore.setState((state) => ({
        creators: state.creators.map((c) =>
          c.uid === uid ? { ...c, sync_status: 'active' } : c,
        ),
      }));
      toast.success('已重新跟进');
      await storeFetchCreators(true);
    } catch { /* interceptor */ }
  }, [storeFetchCreators]);

  const handleBulkAutoSync = useCallback(async (enable: boolean) => {
    const label = enable ? '全部开启自动同步' : '全部关闭自动同步';
    if (creators.length === 0) {
      toast.error('暂无创作者');
      return;
    }
    if (!window.confirm(`确定要对全部 ${creators.length} 位创作者${enable ? '开启' : '关闭'}自动同步吗？`)) {
      return;
    }
    try {
      const result = await bulkSetCreatorAutoSync(enable);
      useStore.setState((state) => ({
        creators: state.creators.map((c) =>
          c.platform === 'local' || c.uid.startsWith('local:')
            ? c
            : { ...c, auto_sync: enable }
        ),
      }));
      toast.success(`${label}完成`, { description: `已更新 ${result.updated} 位创作者` });
    } catch { /* api interceptor handles toast */ }
  }, [creators.length]);

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
      setDeleteAfter(true);
    } catch { /* api interceptor handles toast */ }
    finally { setTranscribing(false); }
  }, [selectedFiles, scannedDirectory, deleteAfter]);

  const totalAssets = creators.reduce((s, c) => s + (c.asset_count || 0), 0);
  const totalTranscribed = creators.reduce((s, c) => s + (c.transcript_completed_count || 0), 0);
  const autoCount = creators.filter(c => c.auto_sync).length;
  const allFilteredSelected =
    filteredCreators.length > 0 && filteredCreators.every((c) => selectedUids.has(c.uid));
  const someFilteredSelected =
    filteredCreators.some((c) => selectedUids.has(c.uid)) && !allFilteredSelected;

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
    removeDialog,
    setRemoveDialog,
    selectedUids,
    bulkBusy,
    allFilteredSelected,
    someFilteredSelected,
    filteredCreators,
    handleAddCreator,
    handleSync,
    handleDeleteCreator,
    executeRemove,
    openBulkRemove,
    toggleSelectUid,
    selectAllFiltered,
    clearSelection,
    toggleSelectAllFiltered,
    handleBulkSetAutoOnSelection,
    handleBulkSyncSelection,
    handleToggleAutoSync,
    handleRefollow,
    handleBulkAutoSync,
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
