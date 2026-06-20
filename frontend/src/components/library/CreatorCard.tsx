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
          <span className="font-mono text-[11px] text-[var(--color-smoke)]">
            #{creator.uid.slice(0, 6)}
          </span>
          <span className={cn(
            'text-[11px] font-medium px-2.5 py-0.5 rounded-full',
            creator.auto_sync ? 'text-[var(--color-rust)] bg-[rgba(0,113,227,0.10)]' : 'text-[var(--color-smoke)] bg-black/5 dark:bg-white/5'
          )}>
            {creator.auto_sync ? '自动' : '手动'}
          </span>
        </div>

        {/* Name */}
        <div className="font-sans font-semibold text-[16px] text-[var(--color-bone)] leading-snug group-hover:text-[var(--color-rust)] transition-colors line-clamp-2 pr-6">
          {creator.nickname || '未命名'}
        </div>
      </div>

      {/* Stats & Progress */}
      <div className="mt-4 pt-3 border-t border-[var(--color-hairline)] flex flex-col gap-2.5">
        <div className="flex items-baseline justify-between">
          <span className="text-[12px] text-[var(--color-ash)] font-medium">
            <span className="font-sans font-semibold text-[14px] text-[var(--color-bone)] mr-1 tabular text-[var(--color-bone)]">{creator.asset_count || 0}</span>
            视频
          </span>
          <span className="text-[12px] text-[var(--color-ash)] font-medium">
            <span className="font-sans font-semibold text-[14px] mr-1 tabular text-[var(--color-rust)]">{creator.transcript_completed_count || 0}</span>
            文稿
          </span>
        </div>
        <div className="w-full h-1.5 bg-black/5 dark:bg-white/10 rounded-full overflow-hidden">
          <div 
            className="h-full bg-[var(--color-rust)] rounded-full transition-all duration-500 ease-out" 
            style={{ width: `${Math.min(100, creator.asset_count ? ((creator.transcript_completed_count || 0) / creator.asset_count) * 100 : 0)}%` }}
          />
        </div>
      </div>

      {/* Hover actions */}
      <div className="absolute top-14 right-4 flex flex-col gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onSync}
          disabled={isSyncing || isDeleting}
          className="w-8 h-8 flex items-center justify-center bg-white/95 dark:bg-zinc-800/95 backdrop-blur border border-[var(--color-hairline-strong)] dark:border-white/10 rounded-[10px] hover:border-[var(--color-rust)] hover:text-[var(--color-rust)] transition-all text-[var(--color-ash)] shadow-sm active:scale-90"
          title="同步"
        >
          {isSyncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
        </button>
        <button
          onClick={onMore}
          disabled={isDeleting}
          className="w-8 h-8 flex items-center justify-center bg-white/95 dark:bg-zinc-800/95 backdrop-blur border border-[var(--color-hairline-strong)] dark:border-white/10 rounded-[10px] hover:border-[var(--color-rust)] hover:text-[var(--color-rust)] transition-all text-[var(--color-ash)] shadow-sm active:scale-90"
          title="更多"
        >
          {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <MoreHorizontal className="w-4 h-4" />}
        </button>
      </div>
    </motion.div>
  );
}
