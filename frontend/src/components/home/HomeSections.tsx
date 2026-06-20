import { motion } from 'framer-motion';
import { type FailureSummary } from '@/services/tasks';


const SPRING = { type: 'spring' as const, stiffness: 260, damping: 24 };

interface FailureSummarySectionProps {
  failureSummary: FailureSummary | null;
}

export function FailureSummarySection({ failureSummary }: FailureSummarySectionProps) {
  if (!failureSummary || failureSummary.total_failed === 0) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING, delay: 0.2 }}
      className="px-6 md:px-10 py-4"
    >
      <div className="home-glass p-6">
        <div className="home-card-head">
          <h2 className="home-card-title flex items-center gap-2">
            <span className="home-pill home-pill-err">
              <span className="home-pill-dot" />
              {failureSummary.total_failed} 次失败
            </span>
          </h2>
          <span className="home-card-meta">过去 {failureSummary.window_days} 日</span>
        </div>
        <div>
          <div className="grid grid-cols-[1fr_auto_auto] gap-5 px-4 pb-2 text-[11px] font-medium tracking-wider uppercase text-[var(--home-fg-muted)]">
            <span>类型</span>
            <span className="text-right w-24">阶段</span>
            <span className="text-right w-10">次数</span>
          </div>
          {failureSummary.buckets.slice(0, 5).map((b) => (
            <div key={b.error_type} className="home-row grid-cols-[1fr_auto_auto]">
              <span className="text-[14px] text-[var(--home-fg)] font-semibold">{b.error_type}</span>
              <span className="font-mono text-[12px] text-[var(--home-fg-soft)] text-right w-24 self-center">{b.error_stage}</span>
              <span className="home-pill home-pill-err w-10 justify-center self-center">
                {b.count}
              </span>
            </div>
          ))}
        </div>
      </div>
    </motion.section>
  );
}

