import { useEffect, useState, useRef, useCallback } from 'react';
import {
  KeyRound, Users, Loader2, ChevronRight, Trash2, FileText, Zap, Info, X, Clock, Plus,
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useStore } from '@/store/useStore';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  cleanupMissingAssets,
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
  runScheduleNow,
} from '@/lib/api';
import type { ScheduleTask } from '@/types';

export default function Settings() {
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

  // Inline remark editing
  const [editingRemark, setEditingRemark] = useState<{ type: string; id: string; value: string } | null>(null);

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
    if (!settings?.status_summary.qwen_ready) return;
    setIsLoadingQwenStatus(true);
    setQwenStatusError('');
    try {
      const res = await getQwenStatus();
      console.log('[QwenStatus] response:', res);
      const map: Record<string, number> = {};
      for (const a of res.accounts || []) {
        map[a.accountId] = a.remaining_hours ?? 0;
      }
      console.log('[QwenStatus] mapped:', map, 'settings ids:', settings?.qwen_accounts?.map((a) => a.id));
      setQwenRemainingHoursById(map);
      if (res.status !== 'success') {
        setQwenStatusError(res.message || '额度服务不可用');
      } else if ((res.accounts || []).length === 0 && (settings?.qwen_accounts?.length || 0) > 0) {
        setQwenStatusError('额度接口返回空账号列表');
      }
    } catch (err) {
      console.error('[QwenStatus] error:', err);
      setQwenStatusError('额度获取失败');
    } finally {
      setIsLoadingQwenStatus(false);
    }
  }, [settings?.status_summary.qwen_ready, settings?.qwen_accounts]);

  useEffect(() => {
    loadQwenStatus();
  }, [loadQwenStatus]);

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

  useEffect(() => {
    loadSchedules();
  }, [loadSchedules]);

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
      setSchedules((prev) =>
        prev.map((s) => (s.task_id === taskId ? { ...s, enabled } : s))
      );
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
    setExportFormat(format);
    try {
      await updateGlobalSettings(autoDeleteVideo, autoTranscribe, format, transcriptOutputDir);
    } catch {
      // revert on error
    }
  }, [autoDeleteVideo, autoTranscribe, transcriptOutputDir]);

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
        map[a.accountId] = a.remaining_hours;
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
      setEditingRemark(null);
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

  if (!settings) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const qwenReady = settings?.status_summary.qwen_ready ?? false;
  const douyinReady = settings?.status_summary.douyin_ready ?? false;
  const bilibiliReady = (settings?.status_summary.bilibili_accounts_count ?? 0) > 0;

  const EXPORT_FORMATS = [
    { value: 'md', label: 'Markdown' },
    { value: 'docx', label: 'Word' },
    { value: 'pdf', label: 'PDF' },
    { value: 'srt', label: 'SRT' },
    { value: 'txt', label: '纯文本' },
  ] as const;

  function SettingsGroup({ title, children }: { title: string; children: React.ReactNode }) {
    return (
      <div className="mb-8">
        <div className="text-caption font-semibold text-muted-foreground uppercase tracking-wide mb-2 px-3">
          {title}
        </div>
        <div className="bg-card rounded-[22px] apple-shadow-widget overflow-hidden">
          {children}
        </div>
      </div>
    );
  }

  function SettingsItem({
    icon, iconBg, label, value, onClick, children, danger,
  }: {
    icon: React.ReactNode;
    iconBg: string;
    label: string;
    value?: React.ReactNode;
    onClick?: () => void;
    children?: React.ReactNode;
    danger?: boolean;
  }) {
    const hasChildren = !!children;
    const isExpanded = expandedSection === label;

    return (
      <div className="border-b border-border/40 last:border-b-0">
        <div
          onClick={() => {
            if (hasChildren) {
              setExpandedSection(isExpanded ? null : label);
            } else if (onClick) {
              onClick();
            }
          }}
          className={cn(
            "flex items-center px-[18px] py-3.5 cursor-pointer transition-colors hover:bg-[rgba(128,128,128,0.04)]",
            danger && "text-destructive"
          )}
        >
          <div className={cn("w-[30px] h-[30px] rounded-lg flex items-center justify-center text-sm mr-3.5 shrink-0", iconBg)}>
            {icon}
          </div>
          <span className="flex-1 text-body">{label}</span>
          {value !== undefined && (
            <span className="text-body text-muted-foreground mr-1">{value}</span>
          )}
          {hasChildren && (
            <ChevronRight className={cn("size-[14px] text-muted-foreground/50 transition-transform", isExpanded && "rotate-90")} />
          )}
          {!hasChildren && onClick && (
            <ChevronRight className="size-[14px] text-muted-foreground/50" />
          )}
        </div>
        <AnimatePresence>
          {hasChildren && isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-4 border-t border-border/40">
                {children}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  }

  function AccountExpandable({
    accounts, cookie, setCookie, remark, setRemark,
    isAdding, cookieError, setCookieError, onAdd, onDelete, onUpdateCookie,
    placeholder, showQuota, accountType,
  }: {
    accounts: Array<{ id: string; status: string; remark: string; last_used: string | null; create_time: string | null }>;
    cookie: string;
    setCookie: (v: string) => void;
    remark: string;
    setRemark: (v: string) => void;
    isAdding: boolean;
    cookieError: string;
    setCookieError: (v: string) => void;
    onAdd: () => void;
    onDelete: (id: string) => void;
    onUpdateCookie?: (id: string, newCookie: string) => void;
    placeholder: string;
    showQuota?: boolean;
    accountType: 'qwen' | 'douyin' | 'bilibili';
  }) {
    const handleStartEditRemark = (id: string, currentRemark: string) => {
      setEditingRemark({ type: accountType, id, value: currentRemark });
    };

    const handleSaveRemarkInline = async () => {
      if (editingRemark) {
        await handleSaveRemark(editingRemark.type, editingRemark.id, editingRemark.value);
      }
    };

    return (
      <div className="pt-3 space-y-3">
        <div className="flex gap-2">
          <input
            type="text"
            placeholder={placeholder}
            value={cookie}
            onChange={(e) => { setCookie(e.target.value); setCookieError(''); }}
            className={cn(
              "flex-1 bg-secondary rounded-lg px-3 py-2 text-sm outline-none border border-transparent focus:border-primary/50",
              cookieError && "border-destructive"
            )}
          />
          <input
            type="text"
            placeholder="备注"
            value={remark}
            onChange={(e) => setRemark(e.target.value)}
            className="w-24 bg-secondary rounded-lg px-3 py-2 text-sm outline-none border border-transparent focus:border-primary/50"
          />
          <button
            onClick={onAdd}
            disabled={!cookie.trim() || isAdding}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-all active:scale-[0.96] disabled:opacity-50"
          >
            {isAdding ? <Loader2 className="size-4 animate-spin" /> : '添加'}
          </button>
        </div>
        {cookieError && <div className="text-xs text-destructive">{cookieError}</div>}

        <div className="space-y-2">
          {accounts.length === 0 ? (
            <div className="text-sm text-muted-foreground py-2">还没有账号</div>
          ) : (
            accounts.map((account, index) => {
              const isEditing = editingRemark?.id === account.id;
              return (
                <div key={account.id} className="flex items-center justify-between py-2 px-3 bg-secondary/50 rounded-lg">
                  <div className="min-w-0 flex-1">
                    {isEditing ? (
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={editingRemark.value}
                          onChange={(e) => setEditingRemark({ ...editingRemark, value: e.target.value })}
                          className="flex-1 bg-background rounded px-2 py-1 text-sm outline-none border border-primary/50"
                          autoFocus
                          onKeyDown={(e) => { if (e.key === 'Enter') handleSaveRemarkInline(); if (e.key === 'Escape') setEditingRemark(null); }}
                        />
                        <button onClick={handleSaveRemarkInline} className="text-xs text-primary font-medium">保存</button>
                        <button onClick={() => setEditingRemark(null)} className="text-xs text-muted-foreground">取消</button>
                      </div>
                    ) : (
                      <div
                        className="text-sm font-medium cursor-pointer hover:text-primary transition-colors"
                        onDoubleClick={() => handleStartEditRemark(account.id, account.remark)}
                        title="双击编辑备注"
                      >
                        {account.remark || `账号 ${index + 1}`}
                      </div>
                    )}
                    <div className="text-xs text-muted-foreground font-mono mt-0.5">
                      {account.id.slice(0, 12)}...
                      {showQuota ? (
                        <span className="ml-2 text-primary">
                          {isLoadingQwenStatus
                            ? '加载中...'
                            : qwenStatusError
                              ? '获取失败'
                              : `${qwenRemainingHoursById[account.id] ?? '--'}h`}
                        </span>
                      ) : (
                        <span className="ml-2 text-muted-foreground">[无额度]</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={cn(
                      "text-small font-semibold px-2 py-0.5 rounded-full",
                      account.status === 'active' ? 'bg-success/12 text-success' : 'bg-warning/14 text-warning'
                    )}>
                      {account.status === 'active' ? '可用' : account.status === 'inactive' ? '停用' : account.status === 'expired' ? '过期' : account.status}
                    </span>
                    {onUpdateCookie && accountType === 'qwen' && (
                      <button
                        onClick={() => {
                          const newCookie = prompt('输入新的 Qwen Cookie:');
                          if (newCookie?.trim()) {
                            onUpdateCookie(account.id, newCookie.trim());
                          }
                        }}
                        className="p-1.5 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                        title="更新 Cookie"
                      >
                        <KeyRound className="size-3.5" />
                      </button>
                    )}
                    <button
                      onClick={() => onDelete(account.id)}
                      disabled={isDeleting === account.id}
                      className="p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                    >
                      {isDeleting === account.id ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {showQuota && qwenReady && (
          <div className="flex items-center justify-between pt-2 border-t border-border/40">
            <span className="text-xs text-muted-foreground">
              {isLoadingQwenStatus
                ? '加载额度中...'
                : qwenStatusError
                  ? `额度: ${qwenStatusError}`
                  : (() => {
                      const total = Object.values(qwenRemainingHoursById).reduce((s, v) => s + v, 0);
                      return `总剩余 ${total}h`;
                    })()}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={loadQwenStatus}
                disabled={isLoadingQwenStatus}
                className="px-3 py-1.5 bg-secondary rounded-lg text-xs font-medium hover:bg-primary hover:text-primary-foreground transition-all active:scale-[0.96] disabled:opacity-50"
                title="刷新额度"
              >
                {isLoadingQwenStatus ? <Loader2 className="size-3 animate-spin" /> : '刷新'}
              </button>
              <button
                onClick={handleClaimQuota}
                disabled={isClaimingQuota}
                className="px-3 py-1.5 bg-secondary rounded-lg text-xs font-medium hover:bg-primary hover:text-primary-foreground transition-all active:scale-[0.96] disabled:opacity-50"
              >
                {isClaimingQuota ? <Loader2 className="size-3 animate-spin" /> : '领取'}
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="h-full p-7 px-8 max-sm:p-4 max-sm:pb-20 overflow-y-auto">
      <div className="text-title-1 mb-6">设置</div>

      <div>
        {/* 账号配置 */}
        <SettingsGroup title="账号配置">
          <SettingsItem
            icon={<Users className="size-4 text-[#FF9500]" />}
            iconBg="bg-[rgba(255,159,10,0.12)]"
            label="抖音 Cookie"
            value={douyinReady ? `${(settings?.douyin_accounts || []).length} 个账号` : '未配置'}
          >
            <AccountExpandable
              accounts={settings?.douyin_accounts || []}
              cookie={douyinCookie}
              setCookie={setDouyinCookie}
              remark={douyinRemark}
              setRemark={setDouyinRemark}
              isAdding={isAddingDouyin}
              cookieError={douyinCookieError}
              setCookieError={setDouyinCookieError}
              onAdd={handleAddDouyin}
              onDelete={(id) => setConfirmDelete({ type: 'douyin', id, name: '抖音账号' })}
              placeholder="粘贴 douyin.com Cookie"
              accountType="douyin"
            />
          </SettingsItem>

          <SettingsItem
            icon={<Users className="size-4 text-[#0A84FF]" />}
            iconBg="bg-[rgba(10,132,255,0.12)]"
            label="B 站 Cookie"
            value={bilibiliReady ? `${(settings?.bilibili_accounts || []).length} 个账号` : '未配置'}
          >
            <AccountExpandable
              accounts={settings?.bilibili_accounts || []}
              cookie={bilibiliCookie}
              setCookie={setBilibiliCookie}
              remark={bilibiliRemark}
              setRemark={setBilibiliRemark}
              isAdding={isAddingBilibili}
              cookieError={bilibiliCookieError}
              setCookieError={setBilibiliCookieError}
              onAdd={handleAddBilibili}
              onDelete={(id) => setConfirmDelete({ type: 'bilibili', id, name: 'B站账号' })}
              placeholder="粘贴 bilibili Cookie"
              accountType="bilibili"
            />
          </SettingsItem>

          <SettingsItem
            icon={<KeyRound className="size-4 text-[#AF52DE]" />}
            iconBg="bg-[rgba(175,82,222,0.12)]"
            label="Qwen 账号池"
            value={qwenReady ? (() => {
              const total = Object.values(qwenRemainingHoursById).reduce((s, v) => s + v, 0);
              return `${total}h / ${(settings?.qwen_accounts || []).length} 个账号`;
            })() : '未配置'}
          >
            <AccountExpandable
              accounts={settings?.qwen_accounts || []}
              cookie={qwenCookie}
              setCookie={setQwenCookie}
              remark={qwenRemark}
              setRemark={setQwenRemark}
              isAdding={isAddingQwen}
              cookieError={qwenCookieError}
              setCookieError={setQwenCookieError}
              onAdd={handleSaveQwen}
              onDelete={(id) => setConfirmDelete({ type: 'qwen', id, name: 'Qwen账号' })}
              onUpdateCookie={handleUpdateQwenCookie}
              placeholder="粘贴 tongyi/qianwen Cookie"
              showQuota={true}
              accountType="qwen"
            />
          </SettingsItem>
        </SettingsGroup>

        {/* 全局偏好 */}
        <SettingsGroup title="全局偏好">
          <SettingsItem
            icon={<Zap className="size-4 text-[#30D158]" />}
            iconBg="bg-[rgba(48,209,88,0.12)]"
            label="自动转写"
            value={
              <Switch checked={autoTranscribe} onCheckedChange={handleToggleAutoTranscribe} />
            }
          />
          <SettingsItem
            icon={<Trash2 className="size-4 text-[#FF453A]" />}
            iconBg="bg-[rgba(255,69,58,0.12)]"
            label="转写后删除视频"
            value={
              <Switch checked={autoDeleteVideo} onCheckedChange={handleToggleAutoDelete} />
            }
          />
          <SettingsItem
            icon={<FileText className="size-4 text-[#0A84FF]" />}
            iconBg="bg-[rgba(10,132,255,0.12)]"
            label="导出格式"
            value={EXPORT_FORMATS.find(f => f.value === exportFormat)?.label || exportFormat}
          >
            <div className="pt-3 grid grid-cols-3 gap-2">
              {EXPORT_FORMATS.map((fmt) => (
                <button
                  key={fmt.value}
                  onClick={() => handleChangeExportFormat(fmt.value)}
                  className={cn(
                    "px-3 py-2 rounded-lg text-sm font-medium transition-all",
                    exportFormat === fmt.value
                      ? "bg-primary text-primary-foreground"
                      : "bg-secondary text-foreground hover:bg-secondary/80"
                  )}
                >
                  {fmt.label}
                </button>
              ))}
            </div>
          </SettingsItem>
          <SettingsItem
            icon={<FileText className="size-4 text-[#30D158]" />}
            iconBg="bg-[rgba(48,209,88,0.12)]"
            label="转写输出目录"
            value={transcriptOutputDir || '默认'}
          >
            <div className="pt-3 space-y-3">
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="留空使用默认目录"
                  value={transcriptOutputDir}
                  onChange={(e) => setTranscriptOutputDir(e.target.value)}
                  className="flex-1 bg-secondary rounded-lg px-3 py-2 text-sm outline-none border border-transparent focus:border-primary/50"
                />
                <button
                  onClick={handleSaveTranscriptOutputDir}
                  className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-all active:scale-[0.96]"
                >
                  保存
                </button>
              </div>
              <div className="text-xs text-muted-foreground">
                默认位置：项目根目录下的 transcripts 文件夹
              </div>
            </div>
          </SettingsItem>
        </SettingsGroup>

        {/* 定时任务 */}
        <SettingsGroup title="定时任务">
          <SettingsItem
            icon={<Clock className="size-4 text-[#FF9500]" />}
            iconBg="bg-[rgba(255,159,10,0.12)]"
            label="同步关注列表"
            value={schedules.length > 0 ? `${schedules.filter(s => s.enabled).length} 个任务` : '未配置'}
          >
            <div className="pt-3 space-y-3">
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Cron 表达式，如 0 2 * * *"
                  value={newCronExpr}
                  onChange={(e) => setNewCronExpr(e.target.value)}
                  className="flex-1 bg-secondary rounded-lg px-3 py-2 text-sm outline-none border border-transparent focus:border-primary/50"
                />
                <button
                  onClick={handleAddSchedule}
                  disabled={!newCronExpr.trim() || isAddingSchedule}
                  className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-all active:scale-[0.96] disabled:opacity-50"
                >
                  {isAddingSchedule ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                </button>
              </div>
              <div className="text-xs text-muted-foreground">
                每天凌晨 2 点: 0 2 * * * · 每 6 小时: 0 */6 * * *
              </div>

              <div className="space-y-2">
                {isLoadingSchedules ? (
                  <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" /> 加载中...
                  </div>
                ) : schedules.length === 0 ? (
                  <div className="text-sm text-muted-foreground py-2">还没有定时任务</div>
                ) : (
                  schedules.map((task) => (
                    <div key={task.task_id} className="flex items-center justify-between py-2 px-3 bg-secondary/50 rounded-lg">
                      <div className="min-w-0">
                        <div className="text-sm font-medium font-mono">{task.cron_expr}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {task.enabled ? '已启用' : '已禁用'} · {task.task_type === 'scan_all_following' ? '同步关注' : task.task_type}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => runScheduleNow(task.task_id).then(() => toast.success('已触发立即执行')).catch(() => toast.error('执行失败'))}
                          className="p-1.5 rounded-lg hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                          title="立即执行"
                        >
                          <Zap className="size-3.5" />
                        </button>
                        <Switch
                          checked={task.enabled}
                          onCheckedChange={(v) => handleToggleSchedule(task.task_id, v)}
                        />
                        <button
                          onClick={() => handleDeleteSchedule(task.task_id)}
                          className="p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </SettingsItem>
        </SettingsGroup>

        {/* 系统 */}
        <SettingsGroup title="系统">
          <SettingsItem
            icon={<Trash2 className="size-4 text-[#FF453A]" />}
            iconBg="bg-[rgba(255,69,58,0.12)]"
            label="清理不存在素材"
            onClick={async () => {
              try {
                const result = await cleanupMissingAssets();
                toast.success(`已清理 ${result.deleted} 条无效记录`);
                useStore.getState().fetchCreators(true);
                refreshSettings();
              } catch { /* interceptor handles toast */ }
            }}
          />
          <SettingsItem
            icon={<Info className="size-4 text-[#5AC8FA]" />}
            iconBg="bg-[rgba(90,200,250,0.12)]"
            label="关于"
            value="v2.0"
          />
        </SettingsGroup>
      </div>

      {/* Delete Confirm Dialog */}
      <AnimatePresence>
        {confirmDelete && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
            onClick={() => setConfirmDelete(null)}
          >
            <motion.div
              initial={{ scale: 0.92, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.92, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              className="bg-card rounded-[22px] p-6 w-full max-w-sm mx-4 shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">删除确认</h3>
                <button onClick={() => setConfirmDelete(null)} className="p-1.5 rounded-lg hover:bg-secondary active:scale-[0.92] transition-colors">
                  <X className="size-4" />
                </button>
              </div>
              <p className="text-sm text-muted-foreground mb-6">
                确定要删除「{confirmDelete.name}」吗？此操作不可撤销。
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setConfirmDelete(null)}
                  className="flex-1 py-2.5 rounded-xl bg-secondary text-sm font-medium hover:bg-secondary/80 transition-colors active:scale-[0.96]"
                >
                  取消
                </button>
                <button
                  onClick={() => {
                    if (confirmDelete.type === 'douyin') handleDeleteDouyin(confirmDelete.id);
                    else if (confirmDelete.type === 'bilibili') handleDeleteBilibili(confirmDelete.id);
                    else if (confirmDelete.type === 'qwen') handleDeleteQwen(confirmDelete.id);
                  }}
                  className="flex-1 py-2.5 rounded-xl bg-destructive text-destructive-foreground text-sm font-medium hover:bg-destructive/90 transition-colors active:scale-[0.96]"
                >
                  删除
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
