import { useEffect, useState, useRef, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { toast } from 'sonner';
import {
  addQwenAccount,
  deleteQwenAccount,
  updateQwenAccountRemark,
  updateQwenAccountCookie,
  addDouyinAccount,
  deleteDouyinAccount,
  updateDouyinAccountRemark,
  addBilibiliAccount,
  deleteBilibiliAccount,
  updateBilibiliAccountRemark,
  updateGlobalSettings,
  getQwenStatus,
  claimQwenQuota,
  getSchedules,
  addSchedule,
  toggleSchedule,
  deleteSchedule,
} from '@/lib/api';
import type { ScheduleTask } from '@/types';

export function useSettings() {
  const settings = useStore((state) => state.settings);
  const fetchSettings = useStore((state) => state.fetchSettings);

  const lastFetchRef = useRef(0);
  const refreshSettings = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && now - lastFetchRef.current < 1000) return;
    lastFetchRef.current = now;
    await fetchSettings();
  }, [fetchSettings]);

  // Account inputs
  const [qwenCookie, setQwenCookie] = useState('');
  const [douyinCookie, setDouyinCookie] = useState('');
  const [bilibiliCookie, setBilibiliCookie] = useState('');
  const [qwenRemark, setQwenRemark] = useState('');
  const [douyinRemark, setDouyinRemark] = useState('');
  const [bilibiliRemark, setBilibiliRemark] = useState('');

  // Loading states
  const [isAddingQwen, setIsAddingQwen] = useState(false);
  const [isAddingDouyin, setIsAddingDouyin] = useState(false);
  const [isAddingBilibili, setIsAddingBilibili] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [isClaimingQuota, setIsClaimingQuota] = useState(false);

  // Errors
  const [qwenCookieError, setQwenCookieError] = useState('');
  const [douyinCookieError, setDouyinCookieError] = useState('');
  const [bilibiliCookieError, setBilibiliCookieError] = useState('');

  // Global settings
  const [autoDeleteVideo, setAutoDeleteVideo] = useState(true);
  const [autoTranscribe, setAutoTranscribe] = useState(true);
  const [exportFormat, setExportFormat] = useState('md');
  const [transcriptOutputDir, setTranscriptOutputDir] = useState('');

  // Quota
  const [qwenRemainingHoursById, setQwenRemainingHoursById] = useState<Record<string, number>>({});
  const [isLoadingQwenStatus, setIsLoadingQwenStatus] = useState(false);
  const [qwenStatusError, setQwenStatusError] = useState('');

  // Scheduler
  const [schedules, setSchedules] = useState<ScheduleTask[]>([]);
  const [isLoadingSchedules, setIsLoadingSchedules] = useState(false);
  const [newCronExpr, setNewCronExpr] = useState('0 2 * * *');
  const [isAddingSchedule, setIsAddingSchedule] = useState(false);

  // Expand
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  // Confirm dialog
  const [confirmDelete, setConfirmDelete] = useState<{ type: string; id: string; name: string } | null>(null);

  const editInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  useEffect(() => {
    if (!settings) return;
    setAutoDeleteVideo(settings.global_settings.auto_delete);
    setAutoTranscribe(settings.global_settings.auto_transcribe);
    setExportFormat(settings.global_settings.export_format || 'md');
    setTranscriptOutputDir(settings.global_settings.transcript_output_dir || '');
  }, [settings]);

  // Load Qwen quota
  const loadQwenStatus = useCallback(async () => {
    if (!settings?.status_summary?.qwen_ready) return;
    setIsLoadingQwenStatus(true);
    setQwenStatusError('');
    try {
      const res = await getQwenStatus();
      const map: Record<string, number> = {};
      for (const a of res.accounts || []) {
        const id = a.account_id;
        if (id) map[id] = a.remaining_hours ?? 0;
      }
      setQwenRemainingHoursById(map);
      if (res.status !== 'success') {
        setQwenStatusError(res.message || '额度服务不可用');
      } else if ((res.accounts || []).length === 0 && (settings?.qwen_accounts?.length || 0) > 0) {
        setQwenStatusError('额度接口返回空账号列表');
      }
    } catch {
      setQwenStatusError('额度获取失败');
    } finally {
      setIsLoadingQwenStatus(false);
    }
  }, [settings?.status_summary?.qwen_ready, settings?.qwen_accounts]);

  useEffect(() => { loadQwenStatus(); }, [loadQwenStatus]);

  // Load schedules
  const loadSchedules = useCallback(async () => {
    setIsLoadingSchedules(true);
    try {
      const data = await getSchedules();
      setSchedules(data);
    } catch {
      toast.error('加载定时任务失败');
    } finally {
      setIsLoadingSchedules(false);
    }
  }, []);

  useEffect(() => { loadSchedules(); }, [loadSchedules]);

  const handleAddSchedule = useCallback(async () => {
    if (!newCronExpr.trim()) return;
    setIsAddingSchedule(true);
    try {
      await addSchedule(newCronExpr.trim(), true);
      toast.success('定时任务添加成功');
      setNewCronExpr('0 2 * * *');
      await loadSchedules();
    } catch {
      toast.error('添加失败，请检查 Cron 表达式格式');
    } finally {
      setIsAddingSchedule(false);
    }
  }, [newCronExpr, loadSchedules]);

  const handleToggleSchedule = useCallback(async (taskId: string, enabled: boolean) => {
    try {
      await toggleSchedule(taskId, enabled);
      setSchedules((prev) => prev.map((s) => (s.task_id === taskId ? { ...s, enabled } : s)));
      toast.success(enabled ? '已启用' : '已禁用');
    } catch {
      toast.error('操作失败');
    }
  }, []);

  const handleDeleteSchedule = useCallback(async (taskId: string) => {
    if (!confirm('确定要删除这个定时任务吗？')) return;
    try {
      await deleteSchedule(taskId);
      setSchedules((prev) => prev.filter((s) => s.task_id !== taskId));
      toast.success('已删除');
    } catch {
      toast.error('删除失败');
    }
  }, []);

  // ===== Actions =====
  const handleSaveQwen = useCallback(async () => {
    if (!qwenCookie.trim()) return;
    setIsAddingQwen(true);
    try {
      await addQwenAccount(qwenCookie.trim(), qwenRemark.trim() || undefined);
      toast.success('Qwen 账号添加成功');
      setQwenCookie('');
      setQwenRemark('');
      await refreshSettings(true);
    } catch {
      setQwenCookieError('添加失败，请检查 Cookie 有效性');
    } finally {
      setIsAddingQwen(false);
    }
  }, [qwenCookie, qwenRemark, refreshSettings]);

  const handleDeleteQwen = useCallback(async (id: string) => {
    setIsDeleting(id);
    try {
      await deleteQwenAccount(id);
      toast.success('已删除');
      await refreshSettings(true);
    } catch {
      toast.error('删除失败');
    } finally {
      setIsDeleting(null);
      setConfirmDelete(null);
    }
  }, [refreshSettings]);

  const handleAddDouyin = useCallback(async () => {
    if (!douyinCookie.trim()) return;
    setIsAddingDouyin(true);
    try {
      await addDouyinAccount(douyinCookie.trim(), douyinRemark.trim() || undefined);
      toast.success('抖音账号添加成功');
      setDouyinCookie('');
      setDouyinRemark('');
      await refreshSettings(true);
    } catch {
      setDouyinCookieError('添加失败，请检查 Cookie 有效性');
    } finally {
      setIsAddingDouyin(false);
    }
  }, [douyinCookie, douyinRemark, refreshSettings]);

  const handleDeleteDouyin = useCallback(async (id: string) => {
    setIsDeleting(id);
    try {
      await deleteDouyinAccount(id);
      toast.success('已删除');
      await refreshSettings(true);
    } catch {
      toast.error('删除失败');
    } finally {
      setIsDeleting(null);
      setConfirmDelete(null);
    }
  }, [refreshSettings]);

  const handleAddBilibili = useCallback(async () => {
    if (!bilibiliCookie.trim()) return;
    setIsAddingBilibili(true);
    try {
      await addBilibiliAccount(bilibiliCookie.trim(), bilibiliRemark.trim() || undefined);
      toast.success('B站账号添加成功');
      setBilibiliCookie('');
      setBilibiliRemark('');
      await refreshSettings(true);
    } catch {
      setBilibiliCookieError('添加失败，请检查 Cookie 有效性');
    } finally {
      setIsAddingBilibili(false);
    }
  }, [bilibiliCookie, bilibiliRemark, refreshSettings]);

  const handleDeleteBilibili = useCallback(async (id: string) => {
    setIsDeleting(id);
    try {
      await deleteBilibiliAccount(id);
      toast.success('已删除');
      await refreshSettings(true);
    } catch {
      toast.error('删除失败');
    } finally {
      setIsDeleting(null);
      setConfirmDelete(null);
    }
  }, [refreshSettings]);

  const handleToggleAutoTranscribe = useCallback(async (value: boolean) => {
    setAutoTranscribe(value);
    try {
      await updateGlobalSettings(autoDeleteVideo, value, exportFormat, transcriptOutputDir);
      toast.success(value ? '已开启自动转写' : '已关闭自动转写');
    } catch {
      setAutoTranscribe(!value);
    }
  }, [autoDeleteVideo, exportFormat, transcriptOutputDir]);

  const handleToggleAutoDelete = useCallback(async (value: boolean) => {
    setAutoDeleteVideo(value);
    try {
      await updateGlobalSettings(value, autoTranscribe, exportFormat, transcriptOutputDir);
      toast.success(value ? '已开启自动删除' : '已关闭自动删除');
    } catch {
      setAutoDeleteVideo(!value);
    }
  }, [autoTranscribe, exportFormat, transcriptOutputDir]);

  const handleChangeExportFormat = useCallback(async (format: string) => {
    const prev = exportFormat;
    setExportFormat(format);
    try {
      await updateGlobalSettings(autoDeleteVideo, autoTranscribe, format, transcriptOutputDir);
    } catch {
      setExportFormat(prev);
    }
  }, [autoDeleteVideo, autoTranscribe, exportFormat, transcriptOutputDir]);

  const handleSaveTranscriptOutputDir = useCallback(async () => {
    try {
      await updateGlobalSettings(autoDeleteVideo, autoTranscribe, exportFormat, transcriptOutputDir);
      toast.success('转写输出目录已保存');
    } catch {
      toast.error('保存失败');
    }
  }, [autoDeleteVideo, autoTranscribe, exportFormat, transcriptOutputDir]);

  const handleClaimQuota = useCallback(async () => {
    setIsClaimingQuota(true);
    try {
      await claimQwenQuota();
      toast.success('额度领取成功');
      const res = await getQwenStatus();
      const map: Record<string, number> = {};
      for (const a of res.accounts || []) {
        const id = a.account_id;
        if (id) map[id] = a.remaining_hours;
      }
      setQwenRemainingHoursById(map);
    } catch {
      toast.error('领取失败');
    } finally {
      setIsClaimingQuota(false);
    }
  }, []);

  const handleSaveRemark = useCallback(async (type: string, id: string, remark: string) => {
    try {
      if (type === 'qwen') await updateQwenAccountRemark(id, remark);
      else if (type === 'douyin') await updateDouyinAccountRemark(id, remark);
      else if (type === 'bilibili') await updateBilibiliAccountRemark(id, remark);
      toast.success('备注已更新');
      await refreshSettings(true);
    } catch {
      toast.error('更新失败');
    }
  }, [refreshSettings]);

  const handleUpdateQwenCookie = useCallback(async (id: string, newCookie: string) => {
    if (!newCookie.trim()) return;
    try {
      await updateQwenAccountCookie(id, newCookie.trim());
      toast.success('Cookie 已更新');
      await refreshSettings(true);
    } catch {
      toast.error('更新失败');
    }
  }, [refreshSettings]);

  return {
    settings,
    refreshSettings,
    qwenCookie,
    setQwenCookie,
    douyinCookie,
    setDouyinCookie,
    bilibiliCookie,
    setBilibiliCookie,
    qwenRemark,
    setQwenRemark,
    douyinRemark,
    setDouyinRemark,
    bilibiliRemark,
    setBilibiliRemark,
    isAddingQwen,
    isAddingDouyin,
    isAddingBilibili,
    isDeleting,
    isClaimingQuota,
    qwenCookieError,
    setQwenCookieError,
    douyinCookieError,
    setDouyinCookieError,
    bilibiliCookieError,
    setBilibiliCookieError,
    autoDeleteVideo,
    autoTranscribe,
    exportFormat,
    setExportFormat,
    transcriptOutputDir,
    setTranscriptOutputDir,
    qwenRemainingHoursById,
    isLoadingQwenStatus,
    qwenStatusError,
    schedules,
    isLoadingSchedules,
    newCronExpr,
    setNewCronExpr,
    isAddingSchedule,
    expandedSection,
    setExpandedSection,
    confirmDelete,
    setConfirmDelete,
    editInputRef,
    handleAddSchedule,
    handleToggleSchedule,
    handleDeleteSchedule,
    handleSaveQwen,
    handleDeleteQwen,
    handleAddDouyin,
    handleDeleteDouyin,
    handleAddBilibili,
    handleDeleteBilibili,
    handleToggleAutoTranscribe,
    handleToggleAutoDelete,
    handleChangeExportFormat,
    handleSaveTranscriptOutputDir,
    handleClaimQuota,
    handleSaveRemark,
    handleUpdateQwenCookie,
  };
}
