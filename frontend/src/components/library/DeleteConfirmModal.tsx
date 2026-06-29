import { AnimatePresence, motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';

interface DeleteConfirmModalProps {
  deleteConfirm: {
    uid: string;
    nickname: string;
    assetCount: number;
    deleteAssets: boolean;
  } | null;
  onClose: () => void;
  deleting: boolean;
  onCheckboxChange: (checked: boolean) => void;
  onConfirm: () => void;
}

export function DeleteConfirmModal({
  deleteConfirm,
  onClose,
  deleting,
  onCheckboxChange,
  onConfirm,
}: DeleteConfirmModalProps) {
  return (
    <AnimatePresence>
      {deleteConfirm && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-md px-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            className="bg-[var(--color-paper)]/95 backdrop-blur-2xl p-7 w-full max-w-md border border-[var(--color-iron)]/30 rounded-2xl shadow-[0_24px_64px_rgba(0,0,0,0.4)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="eyebrow text-[var(--color-iron)] mb-2">不可撤销</div>
            <h3 className="font-sans font-bold text-[28px] text-[var(--color-bone)] leading-tight">
              确认移除？
            </h3>
            <p className="text-[15px] text-[var(--color-ash)] mt-2">
              <span className="text-[var(--color-bone)]">{deleteConfirm.nickname}</span> 将不再被追踪。
            </p>

            {deleteConfirm.assetCount > 0 && (
              <div className="mt-5 pt-5 border-t border-[var(--color-hairline)]">
                <p className="text-[13px] text-[var(--color-ash)]">
                  关联素材：{' '}
                  <span className="font-sans font-bold text-[20px] text-[var(--color-bone)] tabular">{deleteConfirm.assetCount}</span>{' '}
                  个文件
                </p>
                <label className="mt-3 flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={deleteConfirm.deleteAssets}
                    onChange={(e) => onCheckboxChange(e.target.checked)}
                    className="w-4 h-4 accent-[var(--color-iron)]"
                  />
                  <span className="text-[13px] text-[var(--color-bone)]">连同素材一并删除（不可恢复）</span>
                </label>
              </div>
            )}

            <div className="flex gap-2 mt-7">
              <button onClick={onClose} className="flex-1 btn-sharp">取消</button>
              <button
                onClick={onConfirm}
                disabled={deleting}
                className="flex-1 btn-sharp border-[var(--color-iron)] text-[var(--color-iron)] hover:bg-[var(--color-iron)] hover:text-[var(--color-ink)] disabled:opacity-40 flex items-center justify-center gap-2"
              >
                {deleting ? (
                  <><Loader2 className="w-3.5 h-3.5 animate-spin" /> 删除中</>
                ) : (
                  deleteConfirm.deleteAssets ? '删除全部' : '仅删除创作者'
                )}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
