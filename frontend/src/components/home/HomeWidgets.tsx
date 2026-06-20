import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import NumberFlow from '@number-flow/react';

/* ═══════════════════════════════════════════════════════════════
 *  Home v2 widgets — Raycast/Arc skin.
 *  Props contracts are preserved (additions are optional only),
 *  so every existing call site in Home.tsx keeps working.
 * ═══════════════════════════════════════════════════════════════ */

const SPRING = { type: 'spring' as const, stiffness: 260, damping: 24 };

export function HeroNumeral({ value, unit }: { value: number; unit?: string }) {
  return (
    <div className="font-sans text-[clamp(34px,4vw,52px)] font-bold leading-none tracking-[-0.03em] tabular">
      <NumberFlow
        value={value}
        transformTiming={{ duration: 700, easing: 'cubic-bezier(0.2, 0.9, 0.3, 1)' }}
        spinTiming={{ duration: 700, easing: 'cubic-bezier(0.2, 0.9, 0.3, 1)' }}
      />
      {unit && (
        <span className="font-sans text-[0.34em] font-medium tracking-wider ml-1.5 align-top text-[var(--home-fg-muted)]">
          {unit}
        </span>
      )}
    </div>
  );
}

export function HeroCol({
  label,
  value,
  unit,
  sub,
  accent,
  icon,
  index = 0,
}: {
  label: string;
  value: number;
  unit?: string;
  sub: string;
  accent?: boolean;
  icon?: ReactNode;
  index?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING, delay: 0.05 * index }}
      className="home-glass home-glass-interactive p-6 flex flex-col justify-between min-h-[150px]"
    >
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium text-[var(--home-fg-soft)]">{label}</span>
        {icon && (
          <span className="home-grad-chip w-9 h-9 text-[15px]">{icon}</span>
        )}
      </div>
      <div className={accent ? 'home-grad-text' : 'text-[var(--home-fg)]'}>
        <HeroNumeral value={value} unit={unit} />
      </div>
      <div className="text-[12.5px] text-[var(--home-fg-muted)] font-medium leading-none">{sub}</div>
    </motion.div>
  );
}

export function LedgerEntry({
  when,
  kind,
  title,
  status,
}: {
  when: string;
  kind: string;
  title: string;
  status: 'ok' | 'warn' | 'err';
}) {
  const statusMap = {
    ok:   { cls: 'home-pill-ok',   label: '完成' },
    warn: { cls: 'home-pill-warn', label: '部分' },
    err:  { cls: 'home-pill-err',  label: '失败' },
  };
  const s = statusMap[status];
  return (
    <div className="home-row">
      <span className="font-mono text-[11px] text-[var(--home-fg-muted)] tabular w-14 flex-shrink-0">{when}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2.5">
          <span className="text-[14px] text-[var(--home-fg)] font-semibold">{kind}</span>
          <span className="text-[12.5px] text-[var(--home-fg-soft)] truncate">{title}</span>
        </div>
      </div>
      <span className={`home-pill ${s.cls} flex-shrink-0`}>
        <span className="home-pill-dot" />
        {s.label}
      </span>
    </div>
  );
}

export function ActionRow({
  label,
  kbd,
  icon,
  onClick,
}: {
  label: string;
  kbd?: string;
  icon?: ReactNode;
  onClick?: () => void;
}) {
  return (
    <motion.button
      onClick={onClick}
      whileHover={{ scale: 1.01, x: 2 }}
      whileTap={{ scale: 0.98 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      className="home-row group flex items-center justify-between"
    >
      <div className="flex items-center min-w-0 flex-1">
        {icon && (
          <span className="w-9 h-9 rounded-xl bg-black/[0.02] dark:bg-white/[0.03] border border-[var(--home-glass-border)] flex items-center justify-center text-[var(--home-fg-soft)] group-hover:text-[var(--color-rust)] group-hover:border-[var(--home-glass-border-hover)] transition-colors mr-3 flex-shrink-0">
            {icon}
          </span>
        )}
        <span className="text-[14px] text-[var(--home-fg)] font-medium truncate text-left transition-colors group-hover:text-[var(--color-rust)]">
          {label}
        </span>
      </div>
      {kbd ? (
        <span className="home-card-meta font-mono text-[11px] opacity-60">{kbd}</span>
      ) : (
        <span className="text-[11px] text-[var(--color-rust)] opacity-0 group-hover:opacity-100 transition-opacity font-semibold">
          立即执行 →
        </span>
      )}
    </motion.button>
  );
}
