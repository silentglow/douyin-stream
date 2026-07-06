import type React from 'react';
import { Users, KeyRound } from 'lucide-react';
import { SettingsGroup, SettingsItem } from '@/components/settings/SettingsLayout';
import { AccountExpandable } from '@/components/settings/AccountExpandable';
import type { SettingsPayload } from '@/store/slices/settingsSlice';

interface ConfirmDeletePayload {
  type: string;
  id: string;
  name: string;
}

interface AccountSettingsSectionProps {
  settings: SettingsPayload | null;
  douyinReady: boolean;
  douyinCookie: string;
  setDouyinCookie: (v: string) => void;
  douyinRemark: string;
  setDouyinRemark: (v: string) => void;
  isAddingDouyin: boolean;
  douyinCookieError: string;
  setDouyinCookieError: (v: string) => void;
  editingRemarkDouyin: { id: string } | null;
  setEditingRemarkDouyin: (v: { id: string } | null) => void;
  handleAddDouyin: () => void;
  setConfirmDelete: (v: ConfirmDeletePayload | null) => void;
  editingRemarkBilibili: { id: string } | null;
  setEditingRemarkBilibili: (v: { id: string } | null) => void;
  bilibiliReady: boolean;
  bilibiliCookie: string;
  setBilibiliCookie: (v: string) => void;
  bilibiliRemark: string;
  setBilibiliRemark: (v: string) => void;
  isAddingBilibili: boolean;
  bilibiliCookieError: string;
  setBilibiliCookieError: (v: string) => void;
  handleAddBilibili: () => void;
  editingRemarkYoutube: { id: string } | null;
  setEditingRemarkYoutube: (v: { id: string } | null) => void;
  youtubeReady: boolean;
  youtubeCookie: string;
  setYoutubeCookie: (v: string) => void;
  youtubeRemark: string;
  setYoutubeRemark: (v: string) => void;
  isAddingYoutube: boolean;
  youtubeCookieError: string;
  setYoutubeCookieError: (v: string) => void;
  handleAddYoutube: () => void;
  qwenReady: boolean;
  qwenRemainingHoursById: Record<string, number>;
  qwenCookie: string;
  setQwenCookie: (v: string) => void;
  qwenRemark: string;
  setQwenRemark: (v: string) => void;
  isAddingQwen: boolean;
  qwenCookieError: string;
  setQwenCookieError: (v: string) => void;
  handleSaveQwen: () => void;
  handleUpdateQwenCookie: (id: string, cookie: string) => void;
  editingRemarkQwen: { id: string } | null;
  setEditingRemarkQwen: (v: { id: string } | null) => void;
  editInputRef: React.RefObject<HTMLInputElement | null>;
  handleSaveRemark: (platform: string, accountId: string, remark: string) => Promise<void>;
  isLoadingQwenStatus: boolean;
  qwenStatusError: string;
  loadQwenStatus: () => Promise<void>;
  handleClaimQuota: () => Promise<void>;
  isClaimingQuota: boolean;
  isDeleting: string | null;
}

export function AccountSettingsSection({
  settings,
  douyinReady,
  douyinCookie,
  setDouyinCookie,
  douyinRemark,
  setDouyinRemark,
  isAddingDouyin,
  douyinCookieError,
  setDouyinCookieError,
  editingRemarkDouyin,
  setEditingRemarkDouyin,
  handleAddDouyin,
  setConfirmDelete,
  editingRemarkBilibili,
  setEditingRemarkBilibili,
  bilibiliReady,
  bilibiliCookie,
  setBilibiliCookie,
  bilibiliRemark,
  setBilibiliRemark,
  isAddingBilibili,
  bilibiliCookieError,
  setBilibiliCookieError,
  handleAddBilibili,
  editingRemarkYoutube,
  setEditingRemarkYoutube,
  youtubeReady,
  youtubeCookie,
  setYoutubeCookie,
  youtubeRemark,
  setYoutubeRemark,
  isAddingYoutube,
  youtubeCookieError,
  setYoutubeCookieError,
  handleAddYoutube,
  qwenReady,
  qwenRemainingHoursById,
  qwenCookie,
  setQwenCookie,
  qwenRemark,
  setQwenRemark,
  isAddingQwen,
  qwenCookieError,
  setQwenCookieError,
  handleSaveQwen,
  handleUpdateQwenCookie,
  editingRemarkQwen,
  setEditingRemarkQwen,
  editInputRef,
  handleSaveRemark,
  isLoadingQwenStatus,
  qwenStatusError,
  loadQwenStatus,
  handleClaimQuota,
  isClaimingQuota,
  isDeleting,
}: AccountSettingsSectionProps) {
  return (
    <SettingsGroup title="账号">
      <SettingsItem
        icon={<Users className="w-4 h-4 text-warn" />}
        iconBg="bg-warn/10"
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
          editingRemark={editingRemarkDouyin}
          setEditingRemark={setEditingRemarkDouyin}
          editInputRef={editInputRef}
          handleSaveRemark={handleSaveRemark}
          isLoadingQwenStatus={isLoadingQwenStatus}
          qwenStatusError={qwenStatusError}
          qwenRemainingHoursById={qwenRemainingHoursById}
          qwenReady={qwenReady}
          loadQwenStatus={loadQwenStatus}
          handleClaimQuota={handleClaimQuota}
          isClaimingQuota={isClaimingQuota}
          isDeleting={isDeleting}
        />
      </SettingsItem>

      <SettingsItem
        icon={<Users className="w-4 h-4 text-warn" />}
        iconBg="bg-warn/10"
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
          editingRemark={editingRemarkBilibili}
          setEditingRemark={setEditingRemarkBilibili}
          editInputRef={editInputRef}
          handleSaveRemark={handleSaveRemark}
          isLoadingQwenStatus={isLoadingQwenStatus}
          qwenStatusError={qwenStatusError}
          qwenRemainingHoursById={qwenRemainingHoursById}
          qwenReady={qwenReady}
          loadQwenStatus={loadQwenStatus}
          handleClaimQuota={handleClaimQuota}
          isClaimingQuota={isClaimingQuota}
          isDeleting={isDeleting}
        />
      </SettingsItem>

      <SettingsItem
        icon={<Users className="w-4 h-4 text-warn" />}
        iconBg="bg-warn/10"
        label="YouTube Cookie"
        value={youtubeReady ? `${(settings?.youtube_accounts || []).length} 个账号` : '未配置'}
      >
        <AccountExpandable
          accounts={settings?.youtube_accounts || []}
          cookie={youtubeCookie}
          setCookie={setYoutubeCookie}
          remark={youtubeRemark}
          setRemark={setYoutubeRemark}
          isAdding={isAddingYoutube}
          cookieError={youtubeCookieError}
          setCookieError={setYoutubeCookieError}
          onAdd={handleAddYoutube}
          onDelete={(id) => setConfirmDelete({ type: 'youtube', id, name: 'YouTube账号' })}
          placeholder="粘贴 YouTube Cookie"
          accountType="youtube"
          editingRemark={editingRemarkYoutube}
          setEditingRemark={setEditingRemarkYoutube}
          editInputRef={editInputRef}
          handleSaveRemark={handleSaveRemark}
          isLoadingQwenStatus={isLoadingQwenStatus}
          qwenStatusError={qwenStatusError}
          qwenRemainingHoursById={qwenRemainingHoursById}
          qwenReady={qwenReady}
          loadQwenStatus={loadQwenStatus}
          handleClaimQuota={handleClaimQuota}
          isClaimingQuota={isClaimingQuota}
          isDeleting={isDeleting}
        />
      </SettingsItem>

      <SettingsItem
        icon={<KeyRound className="w-4 h-4 text-accent" />}
        iconBg="bg-accent/10"
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
          editingRemark={editingRemarkQwen}
          setEditingRemark={setEditingRemarkQwen}
          editInputRef={editInputRef}
          handleSaveRemark={handleSaveRemark}
          isLoadingQwenStatus={isLoadingQwenStatus}
          qwenStatusError={qwenStatusError}
          qwenRemainingHoursById={qwenRemainingHoursById}
          qwenReady={qwenReady}
          loadQwenStatus={loadQwenStatus}
          handleClaimQuota={handleClaimQuota}
          isClaimingQuota={isClaimingQuota}
          isDeleting={isDeleting}
        />
      </SettingsItem>
    </SettingsGroup>
  );
}
