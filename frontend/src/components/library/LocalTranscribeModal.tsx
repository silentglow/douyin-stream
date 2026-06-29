import { AnimatePresence, motion } from 'framer-motion';
import { Loader2, X } from 'lucide-react';

interface LocalTranscribeModalProps {
  isOpen: boolean;
  scannedFiles: Array<{ path: string; name: string }>;
  selectedFiles: Set<string>;
  transcribing: boolean;
  deleteAfter: boolean;
  onClose: () => void;
  onSelectAll: () => void;
  onClear: () => void;
  onToggleFile: (path: string) => void;
  onToggleDeleteAfter: () => void;
  onStart: () => void;
}

export function LocalTranscribeModal({
  isOpen,
  scannedFiles,
  selectedFiles,
  transcribing,
  deleteAfter,
  onClose,
  onSelectAll,
  onClear,
  onToggleFile,
  onToggleDeleteAfter,
  onStart,
}: LocalTranscribeModalProps) {
  return (
    <AnimatePresence>
      {isOpen && scannedFiles.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-md px-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.96, opacity: 0, y: 8 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.96, opacity: 0, y: 8 }}
            transition={{ type: 'spring', stiffness: 320, damping: 30 }}
            className="bg-[var(--color-paper)]/95 backdrop-blur-2xl w-full max-w-2xl max-h-[85vh] flex flex-col border border-[var(--color-hairline-strong)] rounded-2xl p-6 shadow-[0_24px_64px_rgba(0,0,0,0.4)]"
            onClick={(e) => e.stopPropagation()}
          >
          <div className="flex items-baseline justify-between mb-4 pb-3 border-b border-[var(--color-hairline)] flex-shrink-0">
            <div>
              <div className="eyebrow mb-1">已扫描目录</div>
              <div className="font-sans font-semibold text-[20px] text-[var(--color-bone)]">
                发现 {scannedFiles.length} 个文件
              </div>
            </div>
            <button onClick={onClose} className="text-[var(--color-smoke)] hover:text-[var(--color-rust)]">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex items-center gap-4 mb-3 flex-shrink-0">
            <button onClick={onSelectAll} className="draw-line text-[12px] text-[var(--color-rust)]">全选</button>
            <button onClick={onClear} className="draw-line text-[12px] text-[var(--color-ash)]">清除</button>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto -mx-2">
            {scannedFiles.map((file) => (
              <label key={file.path} className="flex items-center gap-3 px-2 py-2 hover:bg-black/[0.02] dark:hover:bg-white/[0.03] rounded-lg cursor-pointer transition-colors">
                <input
                  type="checkbox"
                  checked={selectedFiles.has(file.path)}
                  onChange={() => onToggleFile(file.path)}
                  className="w-3.5 h-3.5 accent-[var(--color-rust)]"
                />
                <span className="text-[13px] text-[var(--color-bone)] truncate flex-1 font-mono">{file.name}</span>
              </label>
            ))}
          </div>
          <div className="flex items-center justify-between mt-5 pt-4 border-t border-[var(--color-hairline)] flex-shrink-0">
            <div className="flex items-center gap-4">
              <span className="text-[12px] text-[var(--color-ash)]">
                <span className="font-sans font-bold text-[18px] text-[var(--color-rust)] tabular mr-1">{selectedFiles.size}</span>
                / {scannedFiles.length} 已选
              </span>
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={deleteAfter}
                  onChange={onToggleDeleteAfter}
                  className="w-3.5 h-3.5 accent-[var(--color-rust)]"
                />
                <span className="text-[12px] text-[var(--color-ash)]">转写完成后删除本地原文件</span>
              </label>
            </div>
            <div className="flex gap-2">
              <button onClick={onClose} className="btn-sharp">取消</button>
              <button
                onClick={onStart}
                disabled={selectedFiles.size === 0 || transcribing}
                className="btn-sharp btn-primary disabled:opacity-40 flex items-center gap-2"
              >
                {transcribing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                开始转写
              </button>
            </div>
          </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
