import { useEffect, useState } from 'react';
import { Loader2, RefreshCw, MoreHorizontal, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatLastSync, openCreatorHomepage, platformLabel, resolveCreatorHomepage } from '@/lib/format';
import { Switch } from '@/components/ui/switch';
import type { Creator } from '@/types';

interface CreatorRowProps {
  creator: Creator;
  isSyncing: boolean;
  isDeleting: boolean;
  selected: boolean;
  onToggleSelect: () => void;
  onOpen: () => void;
  onSync: (e: React.MouseEvent) => void;
  onToggleAutoSync: () => void;
  onMore: (e: React.MouseEvent) => void;
}

/** DB 有记录但本地工作区明显更少 → 用户可能已外置归档 */
export function archiveHint(creator: Creator): string | null {
  const dbTx = creator.transcript_completed_count || 0;
  const diskTx = creator.disk_transcript_completed_count;
  const dbAssets = creator.asset_count || 0;
  const diskAssets = creator.disk_asset_count;
  if (typeof diskTx === 'number' && dbTx > 0 && diskTx < dbTx) {
    const missing = dbTx - diskTx;
    if (missing >= 1) return `约 ${missing} 篇已外置`;
  }
  if (typeof diskAssets === 'number' && dbAssets > 0 && diskAssets === 0) {
    return '本地为空 · 历史仍在';
  }
  return null;
}

export const CREATOR_COL =
  'grid grid-cols-[2rem_minmax(0,1fr)_4.25rem_4.25rem_4.25rem_5.25rem_2.75rem_5rem] items-center gap-x-2 px-3 sm:px-4';

function CheckBox({
  checked,
  indeterminate,
  onChange,
  title,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      role="checkbox"
      aria-checked={indeterminate ? 'mixed' : checked}
      onClick={(e) => {
        e.stopPropagation();
        onChange();
      }}
      className={cn(
        'ui-press w-4 h-4 rounded border flex items-center justify-center shrink-0',
        checked || indeterminate
          ? 'bg-[var(--color-rust)] border-[var(--color-rust)]'
          : 'border-[var(--color-hairline-strong)] bg-transparent hover:border-[var(--color-ash)]',
      )}
    >
      {checked && !indeterminate && (
        <svg className="ui-check-pop w-2.5 h-2.5 text-white" viewBox="0 0 12 12" fill="none">
          <path d="M2.5 6.2L5 8.7L9.5 3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      {indeterminate && <div className="w-2 h-0.5 rounded bg-white" />}
    </button>
  );
}

export function CreatorRow({
  creator,
  isSyncing,
  isDeleting,
  selected,
  onToggleSelect,
  onOpen,
  onSync,
  onToggleAutoSync,
  onMore,
}: CreatorRowProps) {
  const assets = creator.asset_count || 0;
  const transcripts = creator.transcript_completed_count || 0;
  const diskTx = creator.disk_transcript_completed_count;
  const hint = archiveHint(creator);
  const auto = !!creator.auto_sync;
  const homepage = resolveCreatorHomepage(creator);
  const localLow =
    typeof diskTx === 'number' && transcripts > 0 && diskTx < transcripts;

  // 同步：请求中转圈；结束后再多转半拍，避免“闪一下就停”
  const [syncSpin, setSyncSpin] = useState(false);
  useEffect(() => {
    if (isSyncing) {
      setSyncSpin(true);
      return;
    }
    if (!syncSpin) return;
    const t = window.setTimeout(() => setSyncSpin(false), 420);
    return () => window.clearTimeout(t);
  }, [isSyncing, syncSpin]);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen();
        }
      }}
      className={cn(
        CREATOR_COL,
        'ui-row py-2.5 border-b border-[var(--color-hairline-faint)] cursor-pointer group relative',
        selected
          ? 'bg-[rgba(0,113,227,0.07)] dark:bg-[rgba(53,128,230,0.1)] shadow-[inset_3px_0_0_var(--color-rust)]'
          : 'hover:bg-black/[0.025] dark:hover:bg-white/[0.035]',
        isDeleting && 'opacity-50 pointer-events-none',
      )}
    >
      <div className="flex justify-center">
        <CheckBox checked={selected} onChange={onToggleSelect} title="选择" />
      </div>

      <div className="min-w-0 flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="font-medium text-[13.5px] text-[var(--color-bone)] truncate group-hover:text-[var(--color-rust)] transition-colors">
              {creator.nickname || '未命名'}
            </span>
            <span className="shrink-0 text-[10px] text-[var(--color-smoke)] opacity-80">
              {platformLabel(creator.platform)}
            </span>
            {creator.sync_status === 'unfollowed' && (
              <span className="shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded bg-black/5 dark:bg-white/5 text-[var(--color-smoke)]">
                已停跟
              </span>
            )}
          </div>
          {hint && (
            <div className="text-[10.5px] text-amber-600/90 dark:text-amber-400/80 mt-0.5 truncate" title={hint}>
              {hint}
            </div>
          )}
        </div>
        {homepage && (
          <button
            type="button"
            title="打开博主主页"
            className="ui-press shrink-0 p-1.5 rounded-md text-[var(--color-smoke)] opacity-0 group-hover:opacity-100 hover:text-[var(--color-rust)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06]"
            onClick={(e) => {
              e.stopPropagation();
              openCreatorHomepage(creator);
            }}
          >
            <ExternalLink className="w-3.5 h-3.5" strokeWidth={2} />
          </button>
        )}
      </div>

      <div className="text-right tabular-nums text-[13px] font-medium text-[var(--color-bone)]">
        {assets}
      </div>
      <div className="text-right tabular-nums text-[13px] font-medium text-[var(--color-bone)]">
        {transcripts}
      </div>
      <div
        className={cn(
          'text-right tabular-nums text-[13px] font-medium',
          localLow ? 'text-amber-600 dark:text-amber-400' : 'text-[var(--color-bone)]',
        )}
      >
        {typeof diskTx === 'number' ? diskTx : '—'}
      </div>
      <div
        className="text-right text-[12px] text-[var(--color-ash)] truncate"
        title={creator.last_fetch_time || '从未同步'}
      >
        {formatLastSync(creator.last_fetch_time)}
      </div>

      <div
        className="flex justify-center"
        onClick={(e) => e.stopPropagation()}
        title={auto ? '自动跟进已开' : '自动跟进已关'}
      >
        <Switch
          checked={auto}
          disabled={isDeleting || creator.sync_status === 'unfollowed'}
          onCheckedChange={() => onToggleAutoSync()}
        />
      </div>

      <div className="flex items-center justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          onClick={onSync}
          disabled={isSyncing || isDeleting || creator.sync_status === 'unfollowed'}
          className="ui-press h-8 w-8 rounded-lg inline-flex items-center justify-center text-[var(--color-ash)] hover:text-[var(--color-rust)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] disabled:opacity-40"
          title="增量同步"
        >
          <RefreshCw
            className={cn(
              'w-3.5 h-3.5',
              syncSpin && (isSyncing ? 'ui-sync-spin-loop' : 'ui-sync-spin'),
              syncSpin && 'text-[var(--color-rust)]',
            )}
            strokeWidth={2}
          />
        </button>
        <button
          type="button"
          onClick={onMore}
          disabled={isDeleting}
          className="ui-press h-8 w-8 rounded-lg inline-flex items-center justify-center text-[var(--color-ash)] hover:text-[var(--color-bone)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] disabled:opacity-40"
          title="更多"
        >
          {isDeleting ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <MoreHorizontal className="w-4 h-4" strokeWidth={2} />
          )}
        </button>
      </div>
    </div>
  );
}

export function CreatorListHeader({
  allSelected,
  someSelected,
  onToggleAll,
}: {
  allSelected: boolean;
  someSelected: boolean;
  onToggleAll: () => void;
}) {
  return (
    <div
      className={cn(
        CREATOR_COL,
        'py-2 border-b border-[var(--color-hairline)] bg-[var(--color-paper)]/60 sticky top-0 z-[1]',
      )}
    >
      <div className="flex justify-center">
        <CheckBox
          checked={allSelected}
          indeterminate={someSelected}
          onChange={onToggleAll}
          title="全选当前列表"
        />
      </div>
      <div className="text-[11px] font-medium text-[var(--color-smoke)] tracking-wide">创作者</div>
      <div className="text-[11px] font-medium text-[var(--color-smoke)] text-right">历史</div>
      <div className="text-[11px] font-medium text-[var(--color-smoke)] text-right">文稿</div>
      <div className="text-[11px] font-medium text-[var(--color-smoke)] text-right">本地</div>
      <div className="text-[11px] font-medium text-[var(--color-smoke)] text-right">同步</div>
      <div className="text-[11px] font-medium text-[var(--color-smoke)] text-center">自动</div>
      <div className="text-[11px] font-medium text-[var(--color-smoke)] text-right">操作</div>
    </div>
  );
}
