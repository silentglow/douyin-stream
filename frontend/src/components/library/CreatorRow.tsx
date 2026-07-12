import { Loader2, RefreshCw, MoreHorizontal, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatLastSync, openCreatorHomepage, platformLabel, resolveCreatorHomepage } from '@/lib/format';
import { CreatorAvatar } from '@/components/ui/CreatorAvatar';
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
function archiveHint(creator: Creator): string | null {
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
          <path
            d="M2.5 6.2L5 8.7L9.5 3.5"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
      {indeterminate && <div className="w-2 h-0.5 rounded bg-white" />}
    </button>
  );
}

/** Compact stat chip: bold number + muted unit. */
function Stat({ value, unit, accent }: { value: number; unit: string; accent?: boolean }) {
  return (
    <span className="inline-flex items-baseline gap-0.5">
      <span
        className={cn(
          'tabular-nums font-semibold',
          accent ? 'text-[var(--color-rust)]' : value ? 'text-[var(--color-bone)]' : 'text-[var(--color-smoke)]/60',
        )}
      >
        {value || '—'}
      </span>
      <span className="text-[var(--color-smoke)]">{unit}</span>
    </span>
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
  const pending = creator.transcript_pending_count || 0;
  const diskTx = creator.disk_transcript_completed_count;
  const hint = archiveHint(creator);
  const auto = !!creator.auto_sync;
  const unfollowed = creator.sync_status === 'unfollowed';
  const homepage = resolveCreatorHomepage(creator);
  const localLow = typeof diskTx === 'number' && transcripts > 0 && diskTx < transcripts;
  const pct = assets > 0 ? Math.min(100, Math.round((transcripts / assets) * 100)) : 0;

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
        'ui-row flex items-center gap-3 px-3 sm:px-4 py-2.5 border-b border-[var(--color-hairline-faint)] cursor-pointer group relative',
        selected
          ? 'bg-[rgba(0,113,227,0.07)] dark:bg-[rgba(53,128,230,0.1)] shadow-[inset_3px_0_0_var(--color-rust)]'
          : 'hover:bg-black/[0.025] dark:hover:bg-white/[0.035]',
        isDeleting && 'opacity-50 pointer-events-none',
        unfollowed && 'opacity-70',
      )}
    >
      <div className="flex justify-center">
        <CheckBox checked={selected} onChange={onToggleSelect} title="选择" />
      </div>

      <CreatorAvatar
        name={creator.nickname}
        avatar={creator.avatar}
        platform={creator.platform}
        seed={creator.uid}
        size={36}
      />

      {/* Identity + stats — the information-rich core */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="font-semibold text-[13.5px] text-[var(--color-bone)] truncate group-hover:text-[var(--color-rust)] transition-colors">
            {creator.nickname || '未命名'}
          </span>
          <span className="shrink-0 text-[10px] text-[var(--color-smoke)] opacity-80">
            {platformLabel(creator.platform)}
          </span>
          {unfollowed && (
            <span className="shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded bg-black/5 dark:bg-white/5 text-[var(--color-smoke)]">
              已停跟
            </span>
          )}
          {homepage && (
            <button
              type="button"
              title="打开博主主页"
              className="ui-press shrink-0 p-1 rounded-md text-[var(--color-smoke)] opacity-0 group-hover:opacity-100 hover:text-[var(--color-rust)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06]"
              onClick={(e) => {
                e.stopPropagation();
                openCreatorHomepage(creator);
              }}
            >
              <ExternalLink className="w-3 h-3" strokeWidth={2} />
            </button>
          )}
        </div>
        <div className="flex items-center gap-2.5 mt-0.5 text-[11.5px]">
          <Stat value={assets} unit="收录" />
          <Stat value={transcripts} unit="文稿" />
          {pending > 0 && <Stat value={pending} unit="待转" accent />}
          <span className="text-[var(--color-smoke)]/70">·</span>
          <span
            className={cn('text-[11px]', localLow ? 'text-amber-600 dark:text-amber-400' : 'text-[var(--color-smoke)]')}
            title={hint || creator.last_fetch_time || '从未同步'}
          >
            {hint || formatLastSync(creator.last_fetch_time)}
          </span>
        </div>
      </div>

      {/* Transcription progress — only meaningful when收录 exists */}
      <div className="hidden md:flex flex-col items-end gap-1 w-28 shrink-0">
        {assets > 0 ? (
          <>
            <div className="flex items-baseline gap-1">
              <span className="tabular-nums text-[12px] font-semibold text-[var(--color-bone)]">{pct}%</span>
              <span className="text-[10px] text-[var(--color-smoke)]">已转写</span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-black/[0.06] dark:bg-white/[0.07] overflow-hidden">
              <div
                className="ui-progress-bar h-full rounded-full"
                style={{ width: `${pct}%`, background: 'var(--accent-grad)' }}
              />
            </div>
          </>
        ) : (
          <span className="text-[11px] text-[var(--color-smoke)]/50">未同步</span>
        )}
      </div>

      <div
        className="flex justify-center shrink-0"
        onClick={(e) => e.stopPropagation()}
        title={auto ? '自动跟进已开' : '自动跟进已关'}
      >
        <Switch checked={auto} disabled={isDeleting || unfollowed} onCheckedChange={() => onToggleAutoSync()} />
      </div>

      <div className="flex items-center justify-end gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          onClick={onSync}
          disabled={isSyncing || isDeleting || unfollowed}
          className="ui-press h-8 w-8 rounded-lg inline-flex items-center justify-center text-[var(--color-ash)] hover:text-[var(--color-rust)] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] disabled:opacity-40"
          title="增量同步"
        >
          <RefreshCw
            className={cn('w-3.5 h-3.5', isSyncing && 'ui-sync-spin-loop', isSyncing && 'text-[var(--color-rust)]')}
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
  count,
}: {
  allSelected: boolean;
  someSelected: boolean;
  onToggleAll: () => void;
  count?: number;
}) {
  return (
    <div className="flex items-center gap-3 px-3 sm:px-4 py-2 border-b border-[var(--color-hairline)] bg-[var(--color-paper)]/60 sticky top-0 z-[1]">
      <div className="flex justify-center">
        <CheckBox checked={allSelected} indeterminate={someSelected} onChange={onToggleAll} title="全选当前列表" />
      </div>
      <div className="text-[11px] font-medium text-[var(--color-smoke)] tracking-wide flex-1">
        创作者{typeof count === 'number' ? ` · ${count}` : ''}
      </div>
      <div className="hidden md:block text-[11px] font-medium text-[var(--color-smoke)] w-28 text-right pr-1">转写进度</div>
      <div className="text-[11px] font-medium text-[var(--color-smoke)] w-10 text-center">自动</div>
      <div className="text-[11px] font-medium text-[var(--color-smoke)] w-[68px] text-right">操作</div>
    </div>
  );
}
