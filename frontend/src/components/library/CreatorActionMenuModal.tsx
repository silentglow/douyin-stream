import { AnimatePresence, motion } from 'framer-motion';
import { ExternalLink, RefreshCw, Trash2 } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { openCreatorHomepage, resolveCreatorHomepage } from '@/lib/format';
import type { Creator } from '@/types';

interface CreatorActionMenuModalProps {
  creator: { uid: string; nickname: string } | null;
  /** Full creator row when available — used for homepage / platform. */
  creatorMeta?: Creator | null;
  onClose: () => void;
  onSync: () => void;
  onFullSync: () => void;
  isAutoSync: boolean;
  onToggleAutoSync: () => void;
  onDelete: () => void;
  onRefollow?: () => void;
}

export function CreatorActionMenuModal({
  creator,
  creatorMeta,
  onClose,
  onSync,
  onFullSync,
  isAutoSync,
  onToggleAutoSync,
  onDelete,
  onRefollow,
}: CreatorActionMenuModalProps) {
  const profile = creatorMeta || creator;
  const homepage = profile ? resolveCreatorHomepage(profile) : null;
  const isUnfollowed = creatorMeta?.sync_status === 'unfollowed';

  return (
    <AnimatePresence>
      {creator && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: '100%', opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: '100%', opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="bg-[var(--color-paper)]/95 backdrop-blur-2xl w-full sm:max-w-sm sm:mx-4 border border-[var(--color-hairline-strong)] rounded-2xl overflow-hidden shadow-[0_24px_64px_rgba(0,0,0,0.4)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-5 border-b border-[var(--color-hairline)]">
              <div className="eyebrow mb-1">创作者</div>
              <div className="font-sans font-semibold text-[18px] text-[var(--color-bone)] truncate">{creator.nickname}</div>
              <p className="text-[11px] text-[var(--color-smoke)] mt-2 leading-relaxed">
                同步 = 增量跟进新内容。全量重拉会强制重下全部（含已归档），请尽量避免。
              </p>
            </div>
            <div>
              {homepage && (
                <button
                  type="button"
                  onClick={() => {
                    openCreatorHomepage(profile!);
                    onClose();
                  }}
                  className="w-full flex items-center gap-4 px-5 py-4 hover:bg-black/[0.02] dark:hover:bg-white/[0.03] transition-colors text-left border-b border-[var(--color-hairline-faint)] group"
                >
                  <ExternalLink className="w-4 h-4 text-[var(--color-rust)]" />
                  <div className="text-left min-w-0">
                    <div className="text-[15px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">打开博主主页</div>
                    <div className="text-[11px] text-[var(--color-smoke)] mt-0.5 truncate">{homepage.replace(/^https?:\/\//, '')}</div>
                  </div>
                </button>
              )}
              {isUnfollowed && onRefollow && (
                <button
                  type="button"
                  onClick={() => {
                    onRefollow();
                    onClose();
                  }}
                  className="w-full flex items-center gap-4 px-5 py-4 hover:bg-black/[0.02] dark:hover:bg-white/[0.03] transition-colors text-left border-b border-[var(--color-hairline-faint)] group"
                >
                  <RefreshCw className="w-4 h-4 text-[var(--color-rust)]" />
                  <div className="text-left">
                    <div className="text-[15px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">重新跟进</div>
                    <div className="text-[11px] text-[var(--color-smoke)] mt-0.5">恢复到跟进中 · 文稿本来就在</div>
                  </div>
                </button>
              )}
              {!isUnfollowed && (
                <>
                  <button
                    onClick={onSync}
                    className="w-full flex items-center gap-4 px-5 py-4 hover:bg-black/[0.02] dark:hover:bg-white/[0.03] transition-colors text-left border-b border-[var(--color-hairline-faint)] group"
                  >
                    <RefreshCw className="w-4 h-4 text-[var(--color-rust)]" />
                    <div className="text-left">
                      <div className="text-[15px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">同步（增量）</div>
                      <div className="text-[11px] text-[var(--color-smoke)] mt-0.5">只拉上次之后的新视频 · 不重下历史</div>
                    </div>
                  </button>
                  <button
                    onClick={onFullSync}
                    className="w-full flex items-center gap-4 px-5 py-4 hover:bg-[rgba(239,68,68,0.06)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group"
                  >
                    <RefreshCw className="w-4 h-4 text-[var(--color-iron)]" />
                    <div className="text-left">
                      <div className="text-[15px] text-[var(--color-iron)]">全量重拉</div>
                      <div className="text-[11px] text-[var(--color-smoke)] mt-0.5">危险：会重下全部，忽略本地是否已归档</div>
                    </div>
                  </button>
                  <div className="w-full flex items-center justify-between px-5 py-4 border-b border-[var(--color-hairline-faint)]">
                    <div>
                      <div className="text-[15px] text-[var(--color-bone)]">自动跟进</div>
                      <div className="text-[11px] text-[var(--color-smoke)] mt-0.5">定时增量同步，不会因文件缺失重下</div>
                    </div>
                    <Switch
                      checked={isAutoSync}
                      onCheckedChange={onToggleAutoSync}
                    />
                  </div>
                </>
              )}
              <button
                onClick={onDelete}
                className="w-full flex items-center gap-4 px-5 py-4 hover:bg-[rgba(239,68,68,0.08)] transition-colors text-left group"
              >
                <Trash2 className="w-4 h-4 text-[var(--color-iron)]" />
                <div className="text-left">
                  <div className="text-[15px] text-[var(--color-iron)]">
                    {isUnfollowed ? '彻底删除…' : '移除创作者…'}
                  </div>
                  <div className="text-[11px] text-[var(--color-smoke)] mt-0.5">
                    {isUnfollowed ? '删除创作者与全部文稿记录' : '可选择保留文稿，或彻底删除'}
                  </div>
                </div>
              </button>
            </div>
            <div className="p-3 border-t border-[var(--color-hairline)]">
              <button onClick={onClose} className="w-full btn-sharp">取消</button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
