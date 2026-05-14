import { useEffect, useState, useRef, useCallback } from 'react';
import {
  KeyRound, Users, Loader2, ChevronRight, Trash2, FileText, Zap, Info, X,
} from 'lucide-react';
import { useStore } from '@/store/useStore';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import {
  cleanupMissingAssets,
  addQwenAccount,
  deleteQwenAccount,
  addDouyinAccount,
  deleteDouyinAccount,
  addBilibiliAccount,
  deleteBilibiliAccount,
  updateGlobalSettings,
  getQwenStatus,
  claimQwenQuota,
} from '@/lib/api';

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

  // Quota
  const [qwenRemainingHoursById, setQwenRemainingHoursById] = useState<Record<string, number>>({});
  const [isLoadingQwenStatus, setIsLoadingQwenStatus] = useState(false);

  // Expand
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  // Confirm dialog
  const [confirmDelete, setConfirmDelete] = useState<{ type: string; id: string; name: string } | null>(null);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  useEffect(() => {
    if (!settings) return;
    queueMicrotask(() => {
      setAutoDeleteVideo(settings.global_settings.auto_delete);
      setAutoTranscribe(settings.global_settings.auto_transcribe);
      setExportFormat(settings.global_settings.export_format || 'md');
    });
  }, [settings]);

  // Load Qwen quota
  useEffect(() => {
    if (!settings?.status_summary.qwen_ready) return;
    setIsLoadingQwenStatus(true);
    getQwenStatus().then((res) => {
      const map: Record<string, number> = {};
      for (const a of res.accounts || []) {
        map[a.accountId] = a.remaining_hours;
      }
      setQwenRemainingHoursById(map);
    }).catch(() => {}).finally(() => setIsLoadingQwenStatus(false));
  }, [settings?.status_summary.qwen_ready]);

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
      await updateGlobalSettings(autoDeleteVideo, value, exportFormat);
      toast.success(value ? '已开启自动转写' : '已关闭自动转写');
    } catch {
      setAutoTranscribe(!value);
    }
  }, []);

  const handleToggleAutoDelete = useCallback(async (value: boolean) => {
    setAutoDeleteVideo(value);
    try {
      await updateGlobalSettings(value, autoTranscribe, exportFormat);
      toast.success(value ? '已开启自动删除' : '已关闭自动删除');
    } catch {
      setAutoDeleteVideo(!value);
    }
  }, []);

  const handleChangeExportFormat = useCallback(async (format: string) => {
    setExportFormat(format);
    try {
      await updateGlobalSettings(autoDeleteVideo, autoTranscribe, format);
    } catch {
      // revert on error
    }
  }, []);

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
        <div className="text-[13px] font-semibold text-muted-foreground uppercase tracking-wide mb-2 px-3">
          {title}
        </div>
        <div className="bg-card rounded-[22px] shadow-[0_2px_12px_rgba(0,0,0,0.06),0_0_1px_rgba(0,0,0,0.04)] overflow-hidden">
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
            "flex items-center px-4 py-3.5 cursor-pointer transition-colors hover:bg-secondary/50",
            danger && "text-destructive"
          )}
        >
          <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center text-sm mr-3 shrink-0", iconBg)}>
            {icon}
          </div>
          <span className="flex-1 text-[16px]">{label}</span>
          {value !== undefined && !hasChildren && (
            <span className="text-sm text-muted-foreground mr-1">{value}</span>
          )}
          {hasChildren && (
            <ChevronRight className={cn("size-4 text-muted-foreground transition-transform", isExpanded && "rotate-90")} />
          )}
          {!hasChildren && onClick && (
            <ChevronRight className="size-4 text-muted-foreground" />
          )}
        </div>
        {hasChildren && isExpanded && (
          <div className="px-4 pb-4 border-t border-border/40">
            {children}
          </div>
        )}
      </div>
    );
  }

  function AccountExpandable({
    accounts, cookie, setCookie, remark, setRemark,
    isAdding, cookieError, setCookieError, onAdd, onDelete,
    placeholder, showQuota,
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
    placeholder: string;
    showQuota?: boolean;
  }) {
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
            accounts.map((account, index) => (
              <div key={account.id} className="flex items-center justify-between py-2 px-3 bg-secondary/50 rounded-lg">
                <div className="min-w-0">
                  <div className="text-sm font-medium">
                    {account.remark || `账号 ${index + 1}`}
                  </div>
                  <div className="text-xs text-muted-foreground font-mono mt-0.5">
                    {account.id.slice(0, 12)}...
                    {showQuota && qwenRemainingHoursById[account.id] !== undefined && (
                      <span className="ml-2 text-primary">{qwenRemainingHoursById[account.id]}h</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={cn(
                    "text-[11px] font-semibold px-2 py-0.5 rounded-full",
                    account.status === 'active' ? 'bg-success/12 text-success' : 'bg-warning/14 text-warning'
                  )}>
                    {account.status === 'active' ? '可用' : account.status === 'inactive' ? '停用' : account.status === 'expired' ? '过期' : account.status}
                  </span>
                  <button
                    onClick={() => onDelete(account.id)}
                    disabled={isDeleting === account.id}
                    className="p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                  >
                    {isDeleting === account.id ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {showQuota && qwenReady && (
          <div className="flex items-center justify-between pt-2 border-t border-border/40">
            <span className="text-xs text-muted-foreground">
              {isLoadingQwenStatus ? '加载额度中...' : '可领取今日额度'}
            </span>
            <button
              onClick={handleClaimQuota}
              disabled={isClaimingQuota}
              className="px-3 py-1.5 bg-secondary rounded-lg text-xs font-medium hover:bg-primary hover:text-primary-foreground transition-all active:scale-[0.96] disabled:opacity-50"
            >
              {isClaimingQuota ? <Loader2 className="size-3 animate-spin" /> : '领取'}
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="h-full p-7 px-8 max-sm:p-4 max-sm:pb-20 overflow-y-auto">
      <div className="text-[28px] font-bold mb-6 tracking-tight">设置</div>

      <div className="max-w-2xl">
        {/* 账号配置 */}
        <SettingsGroup title="账号配置">
          <SettingsItem
            icon={<Users className="size-4 text-orange-500" />}
            iconBg="bg-orange-500/10"
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
            />
          </SettingsItem>

          <SettingsItem
            icon={<Users className="size-4 text-blue-500" />}
            iconBg="bg-blue-500/10"
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
            />
          </SettingsItem>

          <SettingsItem
            icon={<KeyRound className="size-4 text-purple-500" />}
            iconBg="bg-purple-500/10"
            label="Qwen 账号池"
            value={qwenReady ? `${(settings?.qwen_accounts || []).length} 个账号` : '未配置'}
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
              placeholder="粘贴 tongyi/qianwen Cookie"
              showQuota
            />
          </SettingsItem>
        </SettingsGroup>

        {/* 全局偏好 */}
        <SettingsGroup title="全局偏好">
          <SettingsItem
            icon={<Zap className="size-4 text-green-500" />}
            iconBg="bg-green-500/10"
            label="自动转写"
            value={
              <Switch checked={autoTranscribe} onCheckedChange={handleToggleAutoTranscribe} />
            }
          />
          <SettingsItem
            icon={<Trash2 className="size-4 text-red-500" />}
            iconBg="bg-red-500/10"
            label="转写后删除视频"
            value={
              <Switch checked={autoDeleteVideo} onCheckedChange={handleToggleAutoDelete} />
            }
          />
          <SettingsItem
            icon={<FileText className="size-4 text-blue-500" />}
            iconBg="bg-blue-500/10"
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
        </SettingsGroup>

        {/* 系统 */}
        <SettingsGroup title="系统">
          <SettingsItem
            icon={<Trash2 className="size-4 text-red-500" />}
            iconBg="bg-red-500/10"
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
            icon={<Info className="size-4 text-teal-500" />}
            iconBg="bg-teal-500/10"
            label="关于"
            value="v2.0"
          />
        </SettingsGroup>
      </div>

      {/* Delete Confirm Dialog */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-card rounded-[22px] p-6 w-full max-w-sm mx-4 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">删除确认</h3>
              <button onClick={() => setConfirmDelete(null)} className="p-1 rounded-lg hover:bg-secondary">
                <X className="size-4" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground mb-6">
              确定要删除「{confirmDelete.name}」吗？此操作不可撤销。
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="flex-1 py-2.5 rounded-xl bg-secondary text-sm font-medium hover:bg-secondary/80 transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => {
                  if (confirmDelete.type === 'douyin') handleDeleteDouyin(confirmDelete.id);
                  else if (confirmDelete.type === 'bilibili') handleDeleteBilibili(confirmDelete.id);
                  else if (confirmDelete.type === 'qwen') handleDeleteQwen(confirmDelete.id);
                }}
                className="flex-1 py-2.5 rounded-xl bg-destructive text-destructive-foreground text-sm font-medium hover:bg-destructive/90 transition-colors"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
