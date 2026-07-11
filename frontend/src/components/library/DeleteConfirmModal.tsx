import { AnimatePresence, motion } from 'framer-motion';
import { Loader2, Archive, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';

export type RemoveMode = 'keep_content' | 'purge';

export type RemoveTarget = {
  uid: string;
  nickname: string;
  assetCount: number;
  transcriptCount: number;
};

interface DeleteConfirmModalProps {
  /** null = closed; one or more creators */
  targets: RemoveTarget[] | null;
  mode: RemoveMode;
  onClose: () => void;
  deleting: boolean;
  onModeChange: (mode: RemoveMode) => void;
  onConfirm: () => void;
}

export function DeleteConfirmModal({
  targets,
  mode,
  onClose,
  deleting,
  onModeChange,
  onConfirm,
}: DeleteConfirmModalProps) {
  if (!targets || targets.length === 0) return null;

  const isBulk = targets.length > 1;
  const assetCount = targets.reduce((s, t) => s + t.assetCount, 0);
  const transcriptCount = targets.reduce((s, t) => s + t.transcriptCount, 0);
  const hasContent = assetCount > 0 || transcriptCount > 0;
  const title = isBulk
    ? `如何处理这 ${targets.length} 位创作者？`
    : `如何处理「${targets[0].nickname}」？`;
  const namePreview = isBulk
    ? targets
        .slice(0, 4)
        .map((t) => t.nickname)
        .join('、') + (targets.length > 4 ? ` 等 ${targets.length} 人` : '')
    : null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm px-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.96, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.96, opacity: 0 }}
          transition={{ type: 'spring', stiffness: 400, damping: 32 }}
          className="bg-[var(--color-paper)] w-full max-w-md border border-[var(--color-hairline)] rounded-2xl shadow-[0_24px_64px_rgba(0,0,0,0.25)] overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="px-6 pt-6 pb-4">
            <h3 className="text-[17px] font-semibold text-[var(--color-bone)] tracking-tight">
              {title}
            </h3>
            {namePreview && (
              <p className="text-[12px] text-[var(--color-smoke)] mt-1 truncate" title={namePreview}>
                {namePreview}
              </p>
            )}
            <p className="text-[13px] text-[var(--color-ash)] mt-1.5 leading-relaxed">
              {hasContent
                ? `合计约 ${assetCount} 条收录、${transcriptCount} 篇文稿。请选择只停跟，还是连内容一起清掉。`
                : isBulk
                  ? '这些创作者几乎没有收录内容。'
                  : '还没有收录内容。移除后将不再出现在内容库中。'}
            </p>
          </div>

          <div className="px-6 space-y-2">
            <button
              type="button"
              onClick={() => onModeChange('keep_content')}
              className={cn(
                'w-full text-left rounded-xl border p-3.5 transition-colors',
                mode === 'keep_content'
                  ? 'border-[var(--color-rust)] bg-[rgba(0,113,227,0.06)]'
                  : 'border-[var(--color-hairline)] hover:border-[var(--color-hairline-strong)]',
              )}
            >
              <div className="flex items-start gap-3">
                <div
                  className={cn(
                    'mt-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0',
                    mode === 'keep_content' ? 'border-[var(--color-rust)]' : 'border-[var(--color-smoke)]',
                  )}
                >
                  {mode === 'keep_content' && (
                    <div className="w-2 h-2 rounded-full bg-[var(--color-rust)]" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Archive className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                    <span className="text-[13.5px] font-semibold text-[var(--color-bone)]">
                      停跟，保留文稿
                    </span>
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-[rgba(0,113,227,0.1)] text-[var(--color-rust)]">
                      推荐
                    </span>
                  </div>
                  <p className="text-[12px] text-[var(--color-ash)] mt-1 leading-relaxed">
                    {isBulk ? '对所选全部' : ''}关闭自动同步并标记「已停跟」。文稿仍可阅读，不删磁盘文件。
                  </p>
                </div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => onModeChange('purge')}
              className={cn(
                'w-full text-left rounded-xl border p-3.5 transition-colors',
                mode === 'purge'
                  ? 'border-[var(--color-iron)] bg-[rgba(239,68,68,0.06)]'
                  : 'border-[var(--color-hairline)] hover:border-[var(--color-hairline-strong)]',
              )}
            >
              <div className="flex items-start gap-3">
                <div
                  className={cn(
                    'mt-0.5 w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0',
                    mode === 'purge' ? 'border-[var(--color-iron)]' : 'border-[var(--color-smoke)]',
                  )}
                >
                  {mode === 'purge' && (
                    <div className="w-2 h-2 rounded-full bg-[var(--color-iron)]" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Trash2 className="w-3.5 h-3.5 text-[var(--color-iron)]" />
                    <span className="text-[13.5px] font-semibold text-[var(--color-bone)]">
                      彻底删除
                    </span>
                  </div>
                  <p className="text-[12px] text-[var(--color-ash)] mt-1 leading-relaxed">
                    删除{isBulk ? '所选创作者' : '创作者'}、库内素材
                    {hasContent ? `（约 ${assetCount} 条）` : ''}
                    ，并尽量清理本地文件。
                    <span className="text-[var(--color-iron)]"> 不可恢复。</span>
                  </p>
                </div>
              </div>
            </button>
          </div>

          <div className="px-6 py-5 flex gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={deleting}
              className="flex-1 h-10 rounded-lg text-[13px] font-medium text-[var(--color-ash)] hover:bg-black/[0.04] dark:hover:bg-white/[0.05] transition-colors"
            >
              取消
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={deleting}
              className={cn(
                'flex-1 h-10 rounded-lg text-[13px] font-medium inline-flex items-center justify-center gap-2 transition-colors disabled:opacity-40',
                mode === 'purge'
                  ? 'bg-[var(--color-iron)] text-white hover:brightness-110'
                  : 'bg-[var(--color-rust)] text-white hover:brightness-110',
              )}
            >
              {deleting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  处理中…
                </>
              ) : mode === 'purge' ? (
                isBulk ? `确认删除 ${targets.length} 人` : '确认彻底删除'
              ) : isBulk ? (
                `确认停跟 ${targets.length} 人`
              ) : (
                '确认停跟并保留'
              )}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
