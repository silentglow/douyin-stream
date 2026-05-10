import { useEffect, useState, useRef, useCallback } from 'react';
import {
  KeyRound,
  Loader2,
  Users,
} from 'lucide-react';
import { useStore } from '@/store/useStore';
import { PageHeader } from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/button';
import { PageShell } from '@/components/layout/PageShell';
import { AccountPoolSection } from './Settings/sections/AccountPoolSection';
import { GlobalSettingsSection } from './Settings/sections/GlobalSettingsSection';
import { FailureSummarySection } from './Settings/sections/FailureSummarySection';
import { SystemStatusBar } from './Settings/sections/SystemStatusBar';
import { DeleteConfirmDialogs } from './Settings/sections/DeleteConfirmDialogs';
import { useSettingsActions } from './Settings/useSettingsActions';

export default function Settings() {
  const settings = useStore((state) => state.settings);
  const fetchSettings = useStore((state) => state.fetchSettings);

  // 带简单去重的 settings 刷新：1 秒内重复调用会被忽略
  const lastFetchRef = useRef(0);
  const refreshSettings = useCallback(async () => {
    const now = Date.now();
    if (now - lastFetchRef.current < 1000) return;
    lastFetchRef.current = now;
    await fetchSettings();
  }, [fetchSettings]);

  const [qwenCookie, setQwenCookie] = useState('');
  const [douyinCookie, setDouyinCookie] = useState('');
  const [bilibiliCookie, setBilibiliCookie] = useState('');
  const [concurrency, setConcurrency] = useState(3);
  const [autoDeleteVideo, setAutoDeleteVideo] = useState(true);
  const [autoTranscribe, setAutoTranscribe] = useState(true);
  const [exportFormat, setExportFormat] = useState('md');
  const [deletingDouyinId, setDeletingDouyinId] = useState<string | null>(null);
  const [deletingBilibiliId, setDeletingBilibiliId] = useState<string | null>(null);
  const [isAddingDouyin, setIsAddingDouyin] = useState(false);
  const [isAddingBilibili, setIsAddingBilibili] = useState(false);
  const [isSavingConcurrency, setIsSavingConcurrency] = useState(false);
  const [douyinRemark, setDouyinRemark] = useState('');
  const [bilibiliRemark, setBilibiliRemark] = useState('');
  const [editingRemarkId, setEditingRemarkId] = useState<string | null>(null);
  const [editingRemarkValue, setEditingRemarkValue] = useState('');
  const editRemarkInputRef = useRef<HTMLInputElement>(null);

  // Validation error states
  const [qwenCookieError, setQwenCookieError] = useState('');
  const [douyinCookieError, setDouyinCookieError] = useState('');
  const [bilibiliCookieError, setBilibiliCookieError] = useState('');

  // Qwen pool state
  const [qwenRemark, setQwenRemark] = useState('');
  const [isAddingQwen, setIsAddingQwen] = useState(false);
  const [deletingQwenId, setDeletingQwenId] = useState<string | null>(null);

  const [isClaimingQuota, setIsClaimingQuota] = useState(false);

  const qwenReady = settings?.status_summary.qwen_ready ?? false;
  const douyinReady = settings?.status_summary.douyin_ready ?? false;
  const bilibiliReady = (settings?.status_summary.bilibili_accounts_count ?? 0) > 0;
  const canDownload = settings?.status_summary.can_download ?? false;
  const douyinPrimaryConfigured = settings?.status_summary.douyin_primary_configured ?? false;
  const douyinCookieSource = settings?.status_summary.douyin_cookie_source ?? 'none';
  const canRunPipeline = settings?.status_summary.can_run_pipeline ?? false;

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  useEffect(() => {
    if (!settings) return;
    queueMicrotask(() => {
      setConcurrency(settings.global_settings.concurrency);
      setAutoDeleteVideo(settings.global_settings.auto_delete);
      setAutoTranscribe(settings.global_settings.auto_transcribe);
      setExportFormat(settings.global_settings.export_format || 'md');
    });
  }, [settings]);

  useEffect(() => {
    if (editingRemarkId && editRemarkInputRef.current) {
      editRemarkInputRef.current.focus();
    }
  }, [editingRemarkId]);

  const {
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
  } = useSettingsActions({
    settings,
    fetchSettings,
    refreshSettings,
    qwenCookie,
    setQwenCookie,
    qwenRemark,
    setQwenRemark,
    setQwenCookieError,
    setIsAddingQwen,
    douyinCookie,
    setDouyinCookie,
    douyinRemark,
    setDouyinRemark,
    setDouyinCookieError,
    setIsAddingDouyin,
    bilibiliCookie,
    setBilibiliCookie,
    bilibiliRemark,
    setBilibiliRemark,
    setBilibiliCookieError,
    setIsAddingBilibili,
    setEditingRemarkId,
    setEditingRemarkValue,
    setIsClaimingQuota,
    autoTranscribe,
    setAutoTranscribe,
    autoDeleteVideo,
    setAutoDeleteVideo,
    concurrency,
    exportFormat,
    setExportFormat,
    setIsSavingConcurrency,
  });

  if (!settings) {
    return (
      <PageShell variant="default">
        <div className="flex items-center justify-center py-20">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell variant="default">
      <div className="flex flex-col gap-6">
        {/* Apple 风格 Header */}
        <PageHeader
          title="设置"
          description="管理账号 Cookie、全局参数和自动化行为。"
        />

        <SystemStatusBar
          douyinReady={douyinReady}
          douyinCookieSource={douyinCookieSource}
          douyinAccountsCount={settings?.status_summary.douyin_accounts_count ?? 0}
          qwenReady={qwenReady}
          qwenAccountsCount={settings?.status_summary.qwen_accounts_count ?? 0}
          bilibiliReady={bilibiliReady}
          bilibiliAccountsCount={settings?.status_summary.bilibili_accounts_count ?? 0}
          canRunPipeline={canRunPipeline}
          canDownload={canDownload}
        />
        {/* 账号池卡片 - Apple 风格 */}
        <div className="w-full grid gap-6 lg:grid-cols-2">
          <AccountPoolSection
            title="抖音账号池"
            icon={<Users className="size-4 text-white" />}
            description="管理用于下载和同步的抖音 Cookie。"
            placeholder="粘贴 douyin.com Cookie"
            accounts={settings?.douyin_accounts || []}
            cookie={douyinCookie}
            setCookie={setDouyinCookie}
            remark={douyinRemark}
            setRemark={setDouyinRemark}
            isAdding={isAddingDouyin}
            cookieError={douyinCookieError}
            setCookieError={setDouyinCookieError}
            onAdd={handleAddDouyin}
            onDelete={(id) => setDeletingDouyinId(id)}
            editingRemarkId={editingRemarkId}
            setEditingRemarkId={setEditingRemarkId}
            editingRemarkValue={editingRemarkValue}
            setEditingRemarkValue={setEditingRemarkValue}
            onSaveRemark={handleSaveRemark}
            extraFooter={
              <div className="text-xs text-muted-foreground">
                {douyinPrimaryConfigured && (settings?.douyin_accounts || []).length > 0
                  ? '账号池优先使用，配置文件 Cookie 作为兜底。'
                  : douyinPrimaryConfigured && (settings?.douyin_accounts || []).length === 0
                    ? '当前使用配置文件中的 Cookie。'
                    : null}
              </div>
            }
          />
          <AccountPoolSection
            title="B站账号池"
            icon={<Users className="size-4 text-white" />}
            description="管理用于下载 B站 的 Cookie。"
            placeholder="粘贴 bilibili Cookie"
            accounts={settings?.bilibili_accounts || []}
            cookie={bilibiliCookie}
            setCookie={setBilibiliCookie}
            remark={bilibiliRemark}
            setRemark={setBilibiliRemark}
            isAdding={isAddingBilibili}
            cookieError={bilibiliCookieError}
            setCookieError={setBilibiliCookieError}
            onAdd={handleAddBilibili}
            onDelete={(id) => setDeletingBilibiliId(id)}
            editingRemarkId={editingRemarkId}
            setEditingRemarkId={setEditingRemarkId}
            editingRemarkValue={editingRemarkValue}
            setEditingRemarkValue={setEditingRemarkValue}
            onSaveRemark={handleSaveRemark}
          />
          <AccountPoolSection
            title="Qwen 账号池"
            icon={<KeyRound className="size-4 text-white" />}
            description="管理用于自动转写的 Qwen Cookie。"
            placeholder="粘贴 tongyi/qianwen Cookie"
            accounts={settings?.qwen_accounts || []}
            cookie={qwenCookie}
            setCookie={setQwenCookie}
            remark={qwenRemark}
            setRemark={setQwenRemark}
            isAdding={isAddingQwen}
            cookieError={qwenCookieError}
            setCookieError={setQwenCookieError}
            onAdd={handleSaveQwen}
            onDelete={(id) => setDeletingQwenId(id)}
            editingRemarkId={editingRemarkId}
            setEditingRemarkId={setEditingRemarkId}
            editingRemarkValue={editingRemarkValue}
            setEditingRemarkValue={setEditingRemarkValue}
            onSaveRemark={handleSaveRemark}
            extraFooter={
              qwenReady ? (
                <div className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {isLoadingQwenStatus ? (
                      <>
                        <Loader2 className="size-3 animate-spin" />
                        加载额度中...
                      </>
                    ) : (
                      <span className="flex gap-3">
                        {(settings?.qwen_accounts || []).map((a) => (
                          <span key={a.id}>
                            {a.remark || a.id.slice(0, 8)}: {qwenRemainingHoursById[a.id] ?? 0}h
                          </span>
                        ))}
                      </span>
                    )}
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleClaimQuota}
                    disabled={isClaimingQuota}
                  >
                    {isClaimingQuota && <Loader2 className="size-4 animate-spin mr-1" />}
                    领取今日额度
                  </Button>
                </div>
              ) : null
            }
          />
        </div>
        <GlobalSettingsSection
          autoTranscribe={autoTranscribe}
          onToggleAutoTranscribe={handleToggleAutoTranscribe}
          autoDeleteVideo={autoDeleteVideo}
          onToggleAutoDelete={handleToggleAutoDelete}
          concurrency={concurrency}
          setConcurrency={setConcurrency}
          isSavingConcurrency={isSavingConcurrency}
          onSaveConcurrency={handleSaveConcurrency}
          exportFormat={exportFormat}
          onChangeExportFormat={handleChangeExportFormat}
          refreshSettings={refreshSettings}
        />
        <FailureSummarySection />
        <DeleteConfirmDialogs
          deletingDouyinId={deletingDouyinId}
          setDeletingDouyinId={setDeletingDouyinId}
          onDeleteDouyin={handleDeleteDouyin}
          deletingQwenId={deletingQwenId}
          setDeletingQwenId={setDeletingQwenId}
          onDeleteQwen={handleDeleteQwen}
          deletingBilibiliId={deletingBilibiliId}
          setDeletingBilibiliId={setDeletingBilibiliId}
          onDeleteBilibili={handleDeleteBilibili}
        />      </div>
    </PageShell>
  );
}
