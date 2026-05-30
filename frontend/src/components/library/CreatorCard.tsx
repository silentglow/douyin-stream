import { motion } from 'framer-motion';
import { Loader2, RefreshCw, MoreHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CreatorCardProps {
  creator: {
    uid: string;
    nickname?: string;
    auto_sync?: boolean | number;
    asset_count?: number;
    transcript_completed_count?: number;
  };
  isSyncing: boolean;
  isDeleting: boolean;
  onClick: () => void;
  onSync: (e: React.MouseEvent) => void;
  onMore: (e: React.MouseEvent) => void;
}

export function CreatorCard({
  creator,
  isSyncing,
  isDeleting,
  onClick,
  onSync,
  onMore,
}: CreatorCardProps) {
  return (
    <motion.div
      layout
      className="ed-card p-5 cursor-pointer group relative flex flex-col justify-between min-h-[160px]"
      onClick={onClick}
    >
      <div>
        {/* Auto/manual badge */}
        <div className="flex justify-between items-center mb-3">
          <span className="text-[10px] font-bold tracking-widest text-[var(--color-smoke)] uppercase">
            #{creator.uid.slice(0, 6)}
          </span>
          <span className={cn(
            'text-[10.5px] font-semibold tracking-wider px-2 py-0.5 rounded-full',
            creator.auto_sync ? 'text-[var(--color-rust)] bg-[rgba(255,106,47,0.08)]' : 'text-[var(--color-smoke)] bg-white/5'
          )}>
            {creator.auto_sync ? '自动' : '手动'}
          </span>
        </div>

        {/* Name */}
        <div className="font-sans font-semibold text-[17px] text-[var(--color-bone)] leading-snug group-hover:text-[var(--color-rust)] transition-colors line-clamp-2 pr-6">
          {creator.nickname || '未命名'}
        </div>
      </div>

      {/* Stats */}
      <div className="mt-4 pt-3 border-t border-[var(--color-hairline-faint)] flex items-baseline justify-between">
        <span className="text-[12.5px] text-[var(--color-ash)]">
          <span className="font-sans font-bold text-[16px] text-[var(--color-bone)] mr-1 tabular">{creator.asset_count || 0}</span>
          视频
        </span>
        <span className="text-[12.5px] text-[var(--color-ash)]">
          <span className="font-sans font-bold text-[16px] text-[var(--color-rust)] mr-1 tabular">{creator.transcript_completed_count || 0}</span>
          文稿
        </span>
      </div>

      {/* Hover actions */}
      <div className="absolute top-14 right-4 flex flex-col gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onSync}
          disabled={isSyncing || isDeleting}
          className="w-8 h-8 flex items-center justify-center bg-[var(--color-vellum)] border border-[var(--color-hairline-strong)] rounded-lg hover:border-[var(--color-rust)] hover:text-[var(--color-rust)] transition-colors text-[var(--color-ash)] shadow-sm"
          title="同步"
        >
          {isSyncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
        </button>
        <button
          onClick={onMore}
          disabled={isDeleting}
          className="w-8 h-8 flex items-center justify-center bg-[var(--color-vellum)] border border-[var(--color-hairline-strong)] rounded-lg hover:border-[var(--color-rust)] hover:text-[var(--color-rust)] transition-colors text-[var(--color-ash)] shadow-sm"
          title="更多"
        >
          {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <MoreHorizontal className="w-4 h-4" />}
        </button>
      </div>
    </motion.div>
  );
}
