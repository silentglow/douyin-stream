import { useState } from 'react';
import { Trash2, Info, X, Clock } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useStore } from '@/store/useStore';
import { toast } from 'sonner';
import { cleanupMissingAssets } from '@/lib/api';
import { useSettings } from '@/hooks/useSettings';
import { SettingsGroup, SettingsItem } from '@/components/settings/SettingsLayout';
import { AccountSettingsSection } from '@/components/settings/AccountSettingsSection';
import { PreferenceSettingsSection } from '@/components/settings/PreferenceSettingsSection';
import { ScheduleSettings } from '@/components/settings/ScheduleSettings';

export default function Settings() {
  const [editingRemarkDouyin, setEditingRemarkDouyin] = useState<{ id: string } | null>(null);
  const [editingRemarkBilibili, setEditingRemarkBilibili] = useState<{ id: string } | null>(null);
  const [editingRemarkQwen, setEditingRemarkQwen] = useState<{ id: string } | null>(null);

  const {
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
  } = useSettings();

  if (!settings) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-[var(--color-smoke)]">加载中...</div>
      </div>
    );
  }

  const qwenReady = settings?.status_summary?.qwen_ready ?? false;
  const douyinReady = settings?.status_summary?.douyin_ready ?? false;
  const bilibiliReady = (settings?.status_summary?.bilibili_accounts_count ?? 0) > 0;

  return (
    <div className="h-full overflow-y-auto page-enter">
      {/* ═══ PRO HEADER ═══════════════════════════════════════════ */}
      <header className="px-10 py-5 border-b border-[var(--color-hairline)] sticky top-0 z-10 backdrop-blur-md bg-[var(--color-ink)]/80">
        <h1 className="font-sans text-[20px] font-bold text-[var(--color-bone)]">
          系统设置
        </h1>
      </header>

      <div className="px-10 py-8 max-w-xl">
        {/* Account Settings Section */}
        <AccountSettingsSection
          settings={settings}
          douyinReady={douyinReady}
          douyinCookie={douyinCookie}
          setDouyinCookie={setDouyinCookie}
          douyinRemark={douyinRemark}
          setDouyinRemark={setDouyinRemark}
          isAddingDouyin={isAddingDouyin}
          douyinCookieError={douyinCookieError}
          setDouyinCookieError={setDouyinCookieError}
          editingRemarkDouyin={editingRemarkDouyin}
          setEditingRemarkDouyin={setEditingRemarkDouyin}
          handleAddDouyin={handleAddDouyin}
          setConfirmDelete={setConfirmDelete}
          editingRemarkBilibili={editingRemarkBilibili}
          setEditingRemarkBilibili={setEditingRemarkBilibili}
          bilibiliReady={bilibiliReady}
          bilibiliCookie={bilibiliCookie}
          setBilibiliCookie={setBilibiliCookie}
          bilibiliRemark={bilibiliRemark}
          setBilibiliRemark={setBilibiliRemark}
          isAddingBilibili={isAddingBilibili}
          bilibiliCookieError={bilibiliCookieError}
          setBilibiliCookieError={setBilibiliCookieError}
          handleAddBilibili={handleAddBilibili}
          qwenReady={qwenReady}
          qwenRemainingHoursById={qwenRemainingHoursById}
          qwenCookie={qwenCookie}
          setQwenCookie={setQwenCookie}
          qwenRemark={qwenRemark}
          setQwenRemark={setQwenRemark}
          isAddingQwen={isAddingQwen}
          qwenCookieError={qwenCookieError}
          setQwenCookieError={setQwenCookieError}
          handleSaveQwen={handleSaveQwen}
          handleUpdateQwenCookie={handleUpdateQwenCookie}
          editingRemarkQwen={editingRemarkQwen}
          setEditingRemarkQwen={setEditingRemarkQwen}
          editInputRef={editInputRef}
          handleSaveRemark={handleSaveRemark}
          isLoadingQwenStatus={isLoadingQwenStatus}
          qwenStatusError={qwenStatusError}
          loadQwenStatus={refreshSettings}
          handleClaimQuota={handleClaimQuota}
          isClaimingQuota={isClaimingQuota}
          isDeleting={isDeleting}
        />

        {/* Preferences Settings Section */}
        <PreferenceSettingsSection
          autoTranscribe={autoTranscribe}
          handleToggleAutoTranscribe={handleToggleAutoTranscribe}
          autoDeleteVideo={autoDeleteVideo}
          handleToggleAutoDelete={handleToggleAutoDelete}
          exportFormat={exportFormat}
          handleChangeExportFormat={handleChangeExportFormat}
          transcriptOutputDir={transcriptOutputDir}
          setTranscriptOutputDir={setTranscriptOutputDir}
          handleSaveTranscriptOutputDir={handleSaveTranscriptOutputDir}
        />

        {/* Scheduler */}
        <SettingsGroup title="定时">
          <SettingsItem
            icon={<Clock className="w-4 h-4 text-warn" />}
            iconBg="bg-warn/10"
            label="同步关注列表"
            value={schedules.length > 0 ? `${schedules.filter(s => s.enabled).length} 个任务` : '未配置'}
          >
            <ScheduleSettings
              schedules={schedules}
              isLoadingSchedules={isLoadingSchedules}
              newCronExpr={newCronExpr}
              setNewCronExpr={setNewCronExpr}
              isAddingSchedule={isAddingSchedule}
              onAddSchedule={handleAddSchedule}
              onToggleSchedule={handleToggleSchedule}
              onDeleteSchedule={handleDeleteSchedule}
            />
          </SettingsItem>
        </SettingsGroup>

        {/* System */}
        <div className="mb-6">
          <div className="text-[12px] font-semibold text-fg-muted tracking-wide mb-3">
            系统
          </div>
          <div className="bg-surface rounded-xl border border-border-subtle overflow-hidden divide-y divide-border-subtle">
            <SettingsItem
              icon={<Trash2 className="w-4 h-4 text-err" />}
              iconBg="bg-err/10"
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
            <div className="flex items-center justify-between px-5 py-4">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                  <Info className="w-4 h-4 text-accent" />
                </div>
                <span className="text-sm text-fg-primary">关于</span>
              </div>
              <span className="text-xs text-fg-muted font-mono">v2.0.0</span>
            </div>
          </div>
        </div>
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
              className="bg-surface rounded-xl p-6 w-full max-w-sm mx-4 shadow-xl border border-border-subtle"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-fg-primary">删除确认</h3>
                <button onClick={() => setConfirmDelete(null)} className="p-1.5 rounded-lg hover:bg-black/[0.04] active:scale-[0.92] transition-colors">
                  <X className="w-4 h-4 text-fg-muted" />
                </button>
              </div>
              <p className="text-sm text-fg-muted mb-6">
                确定要删除「{confirmDelete.name}」吗？此操作不可撤销。
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setConfirmDelete(null)}
                  className="flex-1 py-2.5 rounded-lg bg-sunken text-sm font-medium hover:bg-black/[0.04] transition-colors text-fg-primary"
                >
                  取消
                </button>
                <button
                  onClick={() => {
                    if (confirmDelete.type === 'douyin') handleDeleteDouyin(confirmDelete.id);
                    else if (confirmDelete.type === 'bilibili') handleDeleteBilibili(confirmDelete.id);
                    else if (confirmDelete.type === 'qwen') handleDeleteQwen(confirmDelete.id);
                  }}
                  className="flex-1 py-2.5 rounded-lg bg-err text-white text-sm font-medium hover:brightness-110 transition-all active:scale-[0.96]"
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
