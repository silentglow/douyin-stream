import { KeyRound, Loader2, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Account {
  id: string;
  status: string;
  remark: string;
  last_used: string | null;
  create_time: string | null;
}

interface AccountExpandableProps {
  accounts: Account[];
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
  accountType: 'qwen' | 'douyin' | 'bilibili' | 'youtube';
  editingRemark: { id: string } | null;
  setEditingRemark: (v: { id: string } | null) => void;
  editInputRef: React.RefObject<HTMLInputElement | null>;
  handleSaveRemark: (type: string, id: string, remark: string) => Promise<void>;
  isLoadingQwenStatus: boolean;
  qwenStatusError: string;
  qwenRemainingHoursById: Record<string, number>;
  qwenReady: boolean;
  loadQwenStatus: () => Promise<void>;
  handleClaimQuota: () => Promise<void>;
  isClaimingQuota: boolean;
  isDeleting: string | null;
}

export function AccountExpandable({
  accounts,
  cookie,
  setCookie,
  remark,
  setRemark,
  isAdding,
  cookieError,
  setCookieError,
  onAdd,
  onDelete,
  onUpdateCookie,
  placeholder,
  showQuota,
  accountType,
  editingRemark,
  setEditingRemark,
  editInputRef,
  handleSaveRemark,
  isLoadingQwenStatus,
  qwenStatusError,
  qwenRemainingHoursById,
  qwenReady,
  loadQwenStatus,
  handleClaimQuota,
  isClaimingQuota,
  isDeleting,
}: AccountExpandableProps) {
  const handleStartEditRemark = (id: string, currentRemark: string) => {
    setEditingRemark({ id });
    setTimeout(() => {
      if (editInputRef.current) {
        editInputRef.current.value = currentRemark;
      }
    }, 0);
  };

  const handleSaveRemarkInline = async () => {
    if (editingRemark && editInputRef.current) {
      await handleSaveRemark(accountType, editingRemark.id, editInputRef.current.value);
      setEditingRemark(null);
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
            "flex-1 bg-sunken rounded-lg px-3 py-2 text-sm text-fg-primary outline-none border border-transparent focus:border-accent-dim transition-colors",
            cookieError && "border-err"
          )}
        />
        <input
          type="text"
          placeholder="备注"
          value={remark}
          onChange={(e) => setRemark(e.target.value)}
          className="w-24 bg-sunken rounded-lg px-3 py-2 text-sm text-fg-primary outline-none border border-transparent focus:border-accent-dim transition-colors"
        />
        <button
          onClick={onAdd}
          disabled={!cookie.trim() || isAdding}
          className="px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:brightness-110 transition-all active:scale-[0.96] disabled:opacity-50"
        >
          {isAdding ? <Loader2 className="w-4 h-4 animate-spin" /> : '添加'}
        </button>
      </div>
      {cookieError && <div className="text-xs text-err">{cookieError}</div>}

      <div className="space-y-2">
        {accounts.length === 0 ? (
          <div className="text-sm text-fg-muted py-2">还没有账号</div>
        ) : (
          accounts.map((account, index) => {
            const isEditing = editingRemark?.id === account.id;
            return (
              <div key={account.id} className="flex items-center justify-between py-2 px-3 bg-sunken rounded-lg">
                <div className="min-w-0 flex-1">
                  {isEditing ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        ref={editInputRef}
                        defaultValue=""
                        className="flex-1 bg-surface rounded px-2 py-1 text-sm outline-none border border-accent-dim"
                        autoFocus
                        onKeyDown={(e) => { if (e.key === 'Enter') handleSaveRemarkInline(); if (e.key === 'Escape') setEditingRemark(null); }}
                        onBlur={handleSaveRemarkInline}
                      />
                      <button onMouseDown={() => setEditingRemark(null)} className="text-xs text-fg-muted">取消</button>
                    </div>
                  ) : (
                    <div
                      className="text-sm font-medium text-fg-primary cursor-pointer hover:text-accent transition-colors"
                      onDoubleClick={() => handleStartEditRemark(account.id, account.remark)}
                      title="双击编辑备注"
                    >
                      {account.remark || `账号 ${index + 1}`}
                    </div>
                  )}
                  <div className="text-xs text-fg-muted font-mono mt-0.5">
                    {account.id.slice(0, 12)}...
                    {showQuota ? (
                      <span className="ml-2 text-accent">
                        {isLoadingQwenStatus
                          ? '加载中...'
                          : qwenStatusError
                            ? '获取失败'
                            : `${qwenRemainingHoursById[account.id] ?? '--'}h`}
                      </span>
                    ) : (
                      <span className="ml-2 text-fg-muted">[无额度]</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={cn(
                    "text-[11px] font-semibold px-2 py-0.5 rounded-full",
                    account.status === 'active' ? 'bg-ok/10 text-ok' : 'bg-warn/10 text-warn'
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
                      className="p-1.5 rounded-lg hover:bg-accent/10 text-fg-muted hover:text-accent transition-colors"
                      title="更新 Cookie"
                    >
                      <KeyRound className="w-3.5 h-3.5" />
                    </button>
                  )}
                  <button
                    onClick={() => onDelete(account.id)}
                    disabled={isDeleting === account.id}
                    className="p-1.5 rounded-lg hover:bg-err/10 text-fg-muted hover:text-err transition-colors"
                  >
                    {isDeleting === account.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {showQuota && qwenReady && (
        <div className="flex items-center justify-between pt-2 border-t border-border-subtle">
          <span className="text-xs text-fg-muted">
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
              className="px-3 py-1.5 bg-sunken rounded-lg text-xs font-medium hover:bg-accent hover:text-white transition-all active:scale-[0.96] disabled:opacity-50"
              title="刷新额度"
            >
              {isLoadingQwenStatus ? <Loader2 className="w-3 h-3 animate-spin" /> : '刷新'}
            </button>
            <button
              onClick={handleClaimQuota}
              disabled={isClaimingQuota}
              className="px-3 py-1.5 bg-sunken rounded-lg text-xs font-medium hover:bg-accent hover:text-white transition-all active:scale-[0.96] disabled:opacity-50"
            >
              {isClaimingQuota ? <Loader2 className="w-3 h-3 animate-spin" /> : '领取'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
