import { AnimatePresence, motion } from 'framer-motion';
import { X, Loader2, FileText } from 'lucide-react';
import type { FolderBrowseResult } from '@/lib/api';

interface FolderBrowserModalProps {
  isOpen: boolean;
  assetTitle: string;
  loading: boolean;
  data: FolderBrowseResult | null;
  onClose: () => void;
}

export function FolderBrowserModal({
  isOpen,
  assetTitle,
  loading,
  data,
  onClose,
}: FolderBrowserModalProps) {
  return (
    <AnimatePresence>
      {isOpen && (
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
            className="bg-[var(--color-paper)]/95 backdrop-blur-2xl w-full sm:max-w-lg sm:mx-4 border border-[var(--color-hairline-strong)] rounded-2xl overflow-hidden max-h-[70vh] flex flex-col shadow-[0_24px_64px_rgba(0,0,0,0.4)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-5 border-b border-[var(--color-hairline)] flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="eyebrow mb-1">关联文件夹</div>
                <div className="font-sans font-semibold text-[18px] text-[var(--color-bone)] truncate">{assetTitle}</div>
                <div className="mono-cap mt-1 truncate">{data?.path || '加载中...'}</div>
              </div>
              <button onClick={onClose} className="text-[var(--color-smoke)] hover:text-[var(--color-rust)] flex-shrink-0">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="overflow-y-auto">
              {loading && (
                <div className="py-12 flex items-center justify-center">
                  <Loader2 className="w-4 h-4 text-[var(--color-smoke)] animate-spin" />
                </div>
              )}
              {!loading && data && data.files.length === 0 && (
                <div className="py-12 text-center text-[13px] text-[var(--color-ash)]">文件夹为空</div>
              )}
              {!loading && data && data.files.map((file) => (
                <div key={file.name} className="flex items-center gap-3 px-5 py-3 border-b border-[var(--color-hairline-faint)] last:border-b-0 hover:bg-black/[0.02] dark:hover:bg-white/[0.03] transition-colors">
                  <FileText className="w-4 h-4 text-[var(--color-ash)] shrink-0" strokeWidth={1.5} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] truncate text-[var(--color-bone)] font-mono">{file.name}</div>
                    <div className="mono-cap mt-0.5">{(file.size / 1024).toFixed(1)} KB</div>
                  </div>
                  <span className="mono-cap shrink-0">{file.suffix.replace('.', '')}</span>
                </div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
