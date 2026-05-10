import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
  addDouyinAccount,
  addBilibiliAccount,
  addQwenAccount,
  claimQwenQuota,
  deleteDouyinAccount,
  deleteBilibiliAccount,
  deleteQwenAccount,
  getQwenStatus,
  type QwenStatusAccount,
  getSettings,
  updateDouyinAccountRemark,
  updateBilibiliAccountRemark,
  updateGlobalSettings,
  updateQwenAccountRemark,
} from '@/lib/api';

type SettingsPayload = Awaited<ReturnType<typeof getSettings>>;

interface SettingsState {
  settings: SettingsPayload | null;
  fetchSettings: () => Promise<SettingsPayload | undefined>;
  refreshSettings: () => void;
  qwenCookie: string;
  setQwenCookie: (v: string) => void;
  qwenRemark: string;
  setQwenRemark: (v: string) => void;
  setQwenCookieError: (v: string) => void;
  setIsAddingQwen: (v: boolean) => void;
  douyinCookie: string;
  setDouyinCookie: (v: string) => void;
  douyinRemark: string;
  setDouyinRemark: (v: string) => void;
  setDouyinCookieError: (v: string) => void;
  setIsAddingDouyin: (v: boolean) => void;
  bilibiliCookie: string;
  setBilibiliCookie: (v: string) => void;
  bilibiliRemark: string;
  setBilibiliRemark: (v: string) => void;
  setBilibiliCookieError: (v: string) => void;
  setIsAddingBilibili: (v: boolean) => void;
  setEditingRemarkId: (v: string | null) => void;
  setEditingRemarkValue: (v: string) => void;
  setIsClaimingQuota: (v: boolean) => void;
  autoTranscribe: boolean;
  setAutoTranscribe: (v: boolean) => void;
  autoDeleteVideo: boolean;
  setAutoDeleteVideo: (v: boolean) => void;
  concurrency: number;
  exportFormat: string;
  setExportFormat: (v: string) => void;
  setIsSavingConcurrency: (v: boolean) => void;
}

export function useSettingsActions(state: SettingsState) {
  const [qwenRemainingHoursById, setQwenRemainingHoursById] = useState<Record<string, number>>({});
  const [isLoadingQwenStatus, setIsLoadingQwenStatus] = useState(false);

  const getQwenAccountValidationStatus = (result: unknown): string | null => {
    if (!result || typeof result !== 'object') return null;
    const payload = result as Record<string, unknown>;
    const rawValidation =
      payload.validation ??
      payload.validation_result ??
      payload.validationResult ??
      payload.validationStatus ??
      payload.validate_result ??
      payload.validateResult;

    if (typeof rawValidation === 'string') return rawValidation;
    if (rawValidation && typeof rawValidation === 'object') {
      const nested = rawValidation as Record<string, unknown>;
      const nestedStatus = nested.status ?? nested.result ?? nested.code;
      if (typeof nestedStatus === 'string') return nestedStatus;

      const ok = nested.ok;
      if (typeof ok === 'boolean' && ok) return 'ok';

      const errorType = nested.error_type ?? nested.errorType;
      if (typeof errorType === 'string') {
        if (errorType === 'network') return 'network_error';
        if (errorType === 'auth') return 'auth_invalid';
        return errorType;
      }
    }
    return null;
  };

  useEffect(() => {
    if (!state.settings?.status_summary.qwen_ready) return;
    queueMicrotask(() => setIsLoadingQwenStatus(true));
    getQwenStatus()
      .then((data) => {
        if (data.status === 'success' && Array.isArray(data.accounts)) {
          const map: Record<string, number> = {};
          (data.accounts as QwenStatusAccount[]).forEach((account) => {
            map[account.accountId] = account.remaining_hours;
          });
          setQwenRemainingHoursById(map);
        }
      })
      .catch((err) => { console.error('获取 Qwen 状态失败:', err); })
      .finally(() => setIsLoadingQwenStatus(false));
  }, [state.settings?.status_summary.qwen_ready]);

  const handleSaveQwen = async () => {
    if (!state.qwenCookie.trim()) {
      state.setQwenCookieError('请输入 Cookie');
      return;
    }
    state.setQwenCookieError('');
    state.setIsAddingQwen(true);
    try {
      const result = await addQwenAccount(state.qwenCookie, state.qwenRemark);
      const validationStatus = getQwenAccountValidationStatus(result);
      if (validationStatus === 'network_error') {
        toast.warning('Qwen 账号已添加，但验证时网络异常');
      } else if (validationStatus === 'auth_invalid') {
        toast.error('Qwen Cookie 无效或已过期');
      } else {
        toast.success('Qwen 账号已添加');
      }
      state.setQwenCookie('');
      state.setQwenRemark('');
      state.refreshSettings();
    } catch {
      // interceptor already toasts
    } finally {
      state.setIsAddingQwen(false);
    }
  };

  const handleDeleteQwen = async (id: string) => {
    try {
      await deleteQwenAccount(id);
      toast.success('Qwen 账号已移除');
      state.refreshSettings();
    } catch {
      // interceptor already toasts
    }
  };

  const handleAddDouyin = async () => {
    if (!state.douyinCookie.trim()) {
      state.setDouyinCookieError('请输入 Cookie');
      return;
    }
    state.setDouyinCookieError('');
    state.setIsAddingDouyin(true);
    try {
      await addDouyinAccount(state.douyinCookie, state.douyinRemark);
      toast.success('抖音账号已加入账号池');
      state.setDouyinCookie('');
      state.setDouyinRemark('');
      state.refreshSettings();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      toast.error(`添加抖音账号失败: ${msg}`);
    } finally {
      state.setIsAddingDouyin(false);
    }
  };

  const handleDeleteDouyin = async (id: string) => {
    try {
      await deleteDouyinAccount(id);
      toast.success('抖音账号已移除');
      state.refreshSettings();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      toast.error(`移除抖音账号失败: ${msg}`);
    }
  };

  const handleAddBilibili = async () => {
    if (!state.bilibiliCookie.trim()) {
      state.setBilibiliCookieError('请输入 Cookie');
      return;
    }
    state.setBilibiliCookieError('');
    state.setIsAddingBilibili(true);
    try {
      await addBilibiliAccount(state.bilibiliCookie, state.bilibiliRemark);
      toast.success('B站账号已加入账号池');
      state.setBilibiliCookie('');
      state.setBilibiliRemark('');
      state.refreshSettings();
    } catch {
      // interceptor already toasts
    } finally {
      state.setIsAddingBilibili(false);
    }
  };

  const handleDeleteBilibili = async (id: string) => {
    try {
      await deleteBilibiliAccount(id);
      toast.success('B站账号已移除');
      state.refreshSettings();
    } catch {
      // interceptor already toasts
    }
  };

  const handleSaveRemark = async (accountId: string, remark: string) => {
    const isQwenAccount = (state.settings?.qwen_accounts || []).some((a) => a.id === accountId);
    const isBilibiliAccount = (state.settings?.bilibili_accounts || []).some((a) => a.id === accountId);
    try {
      if (isQwenAccount) {
        await updateQwenAccountRemark(accountId, remark);
      } else if (isBilibiliAccount) {
        await updateBilibiliAccountRemark(accountId, remark);
      } else {
        await updateDouyinAccountRemark(accountId, remark);
      }
      toast.success('备注已更新');
      state.setEditingRemarkId(null);
      state.refreshSettings();
    } catch {
      // interceptor already toasts
    }
  };

  const handleClaimQuota = async () => {
    state.setIsClaimingQuota(true);
    try {
      const result = await claimQwenQuota();
      if (result.status === 'success') {
        toast.success('额度领取成功');
        const data = await getQwenStatus();
        if (data.status === 'success' && Array.isArray(data.accounts)) {
          const map: Record<string, number> = {};
          (data.accounts as QwenStatusAccount[]).forEach((account) => {
            map[account.accountId] = account.remaining_hours;
          });
          setQwenRemainingHoursById(map);
        }
      }
    } catch {
      // interceptor already toasts
    } finally {
      state.setIsClaimingQuota(false);
    }
  };

  const handleToggleAutoTranscribe = async (value: boolean) => {
    state.setAutoTranscribe(value);
    try {
      const currentSettings = state.settings || await state.fetchSettings();
      const currentAutoDelete = currentSettings?.global_settings.auto_delete ?? state.autoDeleteVideo;
      const currentConcurrency = currentSettings?.global_settings.concurrency ?? state.concurrency;
      await updateGlobalSettings(currentConcurrency, currentAutoDelete, value);
      toast.success(value ? '自动转写已开启' : '自动转写已关闭');
      state.refreshSettings();
    } catch {
      state.setAutoTranscribe(!value);
      // interceptor already toasts
    }
  };

  const handleToggleAutoDelete = async (value: boolean) => {
    state.setAutoDeleteVideo(value);
    try {
      const currentSettings = state.settings || await state.fetchSettings();
      const currentAutoTranscribe = currentSettings?.global_settings.auto_transcribe ?? state.autoTranscribe;
      const currentConcurrency = currentSettings?.global_settings.concurrency ?? state.concurrency;
      await updateGlobalSettings(currentConcurrency, value, currentAutoTranscribe);
      toast.success(value ? '自动删除源视频已开启' : '自动删除源视频已关闭');
      state.refreshSettings();
    } catch {
      state.setAutoDeleteVideo(!value);
      // interceptor already toasts
    }
  };

  const handleSaveConcurrency = async () => {
    state.setIsSavingConcurrency(true);
    try {
      await updateGlobalSettings(state.concurrency, state.autoDeleteVideo, state.autoTranscribe, state.exportFormat);
      toast.success('并发数已保存');
      state.refreshSettings();
    } catch {
      // interceptor already toasts
    } finally {
      state.setIsSavingConcurrency(false);
    }
  };

  const handleChangeExportFormat = async (format: string) => {
    const prev = state.exportFormat;
    state.setExportFormat(format);
    try {
      const currentSettings = state.settings || await state.fetchSettings();
      const currentAutoDelete = currentSettings?.global_settings.auto_delete ?? state.autoDeleteVideo;
      const currentAutoTranscribe = currentSettings?.global_settings.auto_transcribe ?? state.autoTranscribe;
      const currentConcurrency = currentSettings?.global_settings.concurrency ?? state.concurrency;
      await updateGlobalSettings(currentConcurrency, currentAutoDelete, currentAutoTranscribe, format);
      toast.success(`导出格式已切换为 ${format.toUpperCase()}`);
      state.refreshSettings();
    } catch {
      state.setExportFormat(prev);
      toast.error('导出格式切换失败');
    }
  };

  return {
    handleSaveQwen,
    handleDeleteQwen,
    handleAddDouyin,
    handleDeleteDouyin,
    handleAddBilibili,
    handleDeleteBilibili,
    handleSaveRemark,
    handleClaimQuota,
    handleToggleAutoTranscribe,
    handleToggleAutoDelete,
    handleSaveConcurrency,
    handleChangeExportFormat,
    isLoadingQwenStatus,
    qwenRemainingHoursById,
  };
}
