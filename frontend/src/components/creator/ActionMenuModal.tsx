import { AnimatePresence, motion } from 'framer-motion';
import {
  FileText, EyeOff, Eye, Star, Download, ExternalLink, FolderOpen, Trash2
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Asset } from '@/types';

interface ActionMenuModalProps {
  asset: Asset | null;
  onClose: () => void;
  onViewTranscript: (asset: Asset) => void;
  onToggleRead: (asset: Asset, e: React.MouseEvent) => void;
  onToggleStar: (asset: Asset, e: React.MouseEvent) => void;
  onExportTranscript: (asset: Asset) => void;
  onViewFile: (asset: Asset) => void;
  onBrowseFolder: (asset: Asset) => void;
  onDeleteAsset: (asset: Asset) => void;
}

export function ActionMenuModal({
  asset,
  onClose,
  onViewTranscript,
  onToggleRead,
  onToggleStar,
  onExportTranscript,
  onViewFile,
  onBrowseFolder,
  onDeleteAsset,
}: ActionMenuModalProps) {
  return (
    <AnimatePresence>
      {asset && (
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
            className="bg-[var(--color-paper)] w-full sm:max-w-sm sm:mx-4 border border-[var(--color-hairline-strong)] overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-5 border-b border-[var(--color-hairline)]">
              <div className="eyebrow mb-1">素材操作</div>
              <div className="font-display text-[20px] text-[var(--color-bone)] line-clamp-2">{asset.title || '未命名视频'}</div>
            </div>
            <div>
              {asset.transcript_status === 'completed' && (
                <button onClick={() => onViewTranscript(asset)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                  <FileText className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                  <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">查看转写</span>
                </button>
              )}
              <button onClick={(e) => onToggleRead(asset, e)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                {asset.is_read ? <EyeOff className="w-3.5 h-3.5 text-[var(--color-ash)]" /> : <Eye className="w-3.5 h-3.5 text-[var(--color-rust)]" />}
                <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">{asset.is_read ? '标记为未读' : '标记为已读'}</span>
              </button>
              <button onClick={(e) => onToggleStar(asset, e)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                <Star className={cn('w-3.5 h-3.5', asset.is_starred ? 'text-[var(--color-ember)] fill-[var(--color-ember)]' : 'text-[var(--color-ash)]')} />
                <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">{asset.is_starred ? '取消收藏' : '收藏'}</span>
              </button>
              {asset.transcript_status === 'completed' && (
                <button onClick={() => onExportTranscript(asset)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                  <Download className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                  <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">导出转写</span>
                </button>
              )}
              <button onClick={() => onViewFile(asset)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                <ExternalLink className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">查看原文件</span>
              </button>
              {asset.folder_path && (
                <button onClick={() => onBrowseFolder(asset)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(243,238,219,0.03)] transition-colors text-left border-b border-[var(--color-hairline-faint)] group">
                  <FolderOpen className="w-3.5 h-3.5 text-[var(--color-rust)]" />
                  <span className="text-[14px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors">浏览文件夹</span>
                </button>
              )}
              <button onClick={() => onDeleteAsset(asset)} className="w-full flex items-center gap-4 px-5 py-3.5 hover:bg-[rgba(178,89,80,0.08)] transition-colors text-left group">
                <Trash2 className="w-3.5 h-3.5 text-[var(--color-iron)]" />
                <span className="text-[14px] text-[var(--color-iron)]">删除素材</span>
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
