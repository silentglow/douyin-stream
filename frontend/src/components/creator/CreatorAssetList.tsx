import { memo } from 'react';
import { Star, MoreHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Asset } from '@/types';

export function StatusLabel({ status, error }: { status: string; error?: string | null }) {
  if (status === 'completed') {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-patina)] tracking-[0.16em] uppercase">
        <span className="status-dot bg-[var(--color-patina)]" />已转写
      </span>
    );
  }
  if (status === 'failed' || error) {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-iron)] tracking-[0.16em] uppercase max-w-[160px] truncate">
        <span className="status-dot bg-[var(--color-iron)]" />{error ? '失败' : '失败'}
      </span>
    );
  }
  if (status === 'pending' || status === 'queued' || status === 'none' || !status) {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-smoke)] tracking-[0.16em] uppercase">
        <span className="status-dot bg-[var(--color-smoke)]" />待转写
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-[var(--color-rust)] tracking-[0.16em] uppercase">
      <span className="status-dot bg-[var(--color-rust)] pulse-dot" />转写中
    </span>
  );
}

export interface AssetListItemProps {
  asset: Asset;
  bulkMode: boolean;
  isSelected: boolean;
  onToggleSelect: (id: string) => void;
  onViewTranscript: (asset: Asset) => void;
  onToggleStar: (asset: Asset, e: React.MouseEvent) => void;
  onOpenMenu: (asset: Asset) => void;
}

export const AssetListItem = memo(function AssetListItem({
  asset, bulkMode, isSelected, onToggleSelect, onViewTranscript, onToggleStar, onOpenMenu,
}: AssetListItemProps) {
  const canView = asset.transcript_status === 'completed' && asset.transcript_path;
  return (
    <div
      className={cn(
        'grid grid-cols-[auto_1fr_auto] items-center gap-4 px-6 py-4 border-b border-[var(--color-hairline-faint)] transition-colors group relative',
        canView || bulkMode ? 'cursor-pointer' : 'cursor-default',
        isSelected ? 'bg-[rgba(99,102,241,0.06)]' : 'hover:bg-[rgba(255,255,255,0.015)]',
        asset.transcript_status === 'failed' && 'before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[2.5px] before:bg-[var(--color-iron)]'
      )}
      onClick={() => {
        if (bulkMode) onToggleSelect(asset.asset_id);
        else if (canView) onViewTranscript(asset);
      }}
    >
      {/* Checkbox in bulk mode */}
      {bulkMode ? (
        <div className={cn(
          'w-4 h-4 border rounded flex items-center justify-center shrink-0 transition-all',
          isSelected
            ? 'bg-[var(--color-rust)] border-[var(--color-rust)] shadow-sm shadow-[var(--color-rust)]/20'
            : 'border-[var(--color-hairline-strong)]'
        )}>
          {isSelected && (
            <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          )}
        </div>
      ) : (
        <div className="w-4 flex-shrink-0">
          {!asset.is_read && asset.transcript_status === 'completed' && (
            <span className="w-2 h-2 rounded-full bg-[var(--color-rust)] block shadow-[0_0_8px_rgba(99,102,241,0.6)] animate-pulse" />
          )}
        </div>
      )}

      {/* Title + meta */}
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          {asset.is_starred && (
            <Star className="w-3.5 h-3.5 text-[var(--color-ember)] fill-[var(--color-ember)] flex-shrink-0 self-center" />
          )}
          <div className={cn(
            'font-sans font-medium text-[15.5px] leading-snug line-clamp-1 transition-colors',
            canView
              ? 'text-[var(--color-bone)] group-hover:text-[var(--color-rust)]'
              : 'text-[var(--color-ash)]'
          )}>
            {asset.title || '未命名视频'}
          </div>
        </div>
        <div className="mono-cap mt-1.5 flex items-center gap-2">
          {asset.create_time && (
            <span>{new Date(asset.create_time).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })}</span>
          )}
          {asset.transcript_status === 'running' && asset.transcript_retry_count ? (
            <>
              <span className="text-[var(--color-smoke)]">·</span>
              <span>重试 {asset.transcript_retry_count}</span>
            </>
          ) : null}
        </div>
      </div>

      {/* Status + actions */}
      <div className="flex items-center gap-4 flex-shrink-0">
        <StatusLabel status={asset.transcript_status} error={asset.transcript_last_error} />
        {!bulkMode && (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={(e) => onToggleStar(asset, e)}
              className="w-8 h-8 rounded-lg bg-white/[0.02] border border-transparent hover:border-[var(--color-hairline)] flex items-center justify-center text-[var(--color-ash)] hover:text-[var(--color-ember)] transition-all shadow-sm"
              title={asset.is_starred ? '取消收藏' : '收藏'}
            >
              <Star className={cn('w-4 h-4', asset.is_starred && 'fill-[var(--color-ember)] text-[var(--color-ember)]')} strokeWidth={1.5} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onOpenMenu(asset); }}
              className="w-8 h-8 rounded-lg bg-white/[0.02] border border-transparent hover:border-[var(--color-hairline)] flex items-center justify-center text-[var(--color-ash)] hover:text-[var(--color-rust)] transition-all shadow-sm"
              title="更多"
            >
              <MoreHorizontal className="w-4 h-4" strokeWidth={1.5} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
});
