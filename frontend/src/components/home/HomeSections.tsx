import { type FailureSummary } from '@/services/tasks';

interface FailureSummarySectionProps {
  failureSummary: FailureSummary | null;
}

export function FailureSummarySection({ failureSummary }: FailureSummarySectionProps) {
  if (!failureSummary || failureSummary.total_failed === 0) return null;

  return (
    <section className="px-10 py-12 border-b border-[var(--color-hairline)]">
      <div className="flex items-baseline justify-between mb-5 pb-3 border-b border-[var(--color-hairline-strong)]">
        <h2 className="font-display text-[28px] text-[var(--color-iron)] leading-none">失败摘要</h2>
        <span className="mono-cap">
          过去 {failureSummary.window_days} 日 · {failureSummary.total_failed} 次
        </span>
      </div>
      <table className="ed-table">
        <thead>
          <tr>
            <th>类型</th>
            <th>阶段</th>
            <th className="text-right">次数</th>
          </tr>
        </thead>
        <tbody>
          {failureSummary.buckets.slice(0, 5).map((b) => (
            <tr key={b.error_type}>
              <td className="text-[14px] text-[var(--color-bone)] font-medium">{b.error_type}</td>
              <td className="font-mono text-[12px] text-[var(--color-ash)]">{b.error_stage}</td>
              <td className="text-right">
                <span className="font-sans font-bold text-[18px] text-[var(--color-iron)] tabular">
                  {b.count}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

interface RecentTranscriptsSectionProps {
  recentTranscripts: any[];
  onNavigateToTranscripts: () => void;
}

export function RecentTranscriptsSection({
  recentTranscripts,
  onNavigateToTranscripts,
}: RecentTranscriptsSectionProps) {
  if (recentTranscripts.length === 0) return null;

  return (
    <section className="px-10 py-12">
      <div className="flex items-baseline justify-between mb-5 pb-3 border-b border-[var(--color-hairline-strong)]">
        <h2 className="font-display text-[28px] text-[var(--color-bone)] leading-none">最近文稿</h2>
        <button
          onClick={onNavigateToTranscripts}
          className="draw-line text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)] transition-colors"
        >
          全部文稿 →
        </button>
      </div>
      <div className="space-y-1">
        {recentTranscripts.map((t) => (
          <button
            key={t.asset_id}
            onClick={onNavigateToTranscripts}
            className="w-full grid grid-cols-[1fr_auto] gap-5 py-4 border-b border-[var(--color-hairline-faint)] last:border-b-0 items-baseline text-left hover:bg-[rgba(255,255,255,0.015)] rounded-lg transition-colors -mx-3 px-3 cursor-pointer"
          >
            <div className="min-w-0">
              <div className="text-[14.5px] text-[var(--color-bone)] font-medium leading-snug truncate">
                {t.title || '未命名'}
              </div>
              <div className="mono-cap mt-1">
                {t.creator_name || '本地'} · {new Date(t.create_time).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}
              </div>
            </div>
            <span className="text-[10px] tracking-[0.16em] uppercase text-[var(--color-patina)] font-bold">
              已就绪
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
