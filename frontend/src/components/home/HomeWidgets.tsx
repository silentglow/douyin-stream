import NumberFlow from '@number-flow/react';

export function HeroNumeral({ value, unit }: { value: number; unit?: string }) {
  return (
    <div className="numeral text-[clamp(48px,6.5vw,88px)]">
      <NumberFlow
        value={value}
        transformTiming={{ duration: 700, easing: 'cubic-bezier(0.2, 0.9, 0.3, 1)' }}
        spinTiming={{ duration: 700, easing: 'cubic-bezier(0.2, 0.9, 0.3, 1)' }}
      />
      {unit && (
        <span className="font-sans text-[0.24em] font-medium tracking-wider ml-1.5 align-top text-[var(--color-ash)]">
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
}: {
  label: string;
  value: number;
  unit?: string;
  sub: string;
  accent?: boolean;
}) {
  return (
    <div className="bg-[var(--color-paper)] border border-white/[0.03] hover:border-[var(--color-rust)]/25 hover:bg-[rgba(255,106,47,0.02)] hover:shadow-[0_8px_30px_rgba(0,0,0,0.2)] rounded-[var(--radius-card)] p-6 transition-all duration-300 flex flex-col justify-between min-h-[148px]">
      <div>
        <div className="text-[10px] font-bold tracking-widest text-[var(--color-smoke)] uppercase mb-2">{label}</div>
        <div className={accent ? 'text-[var(--color-rust)]' : 'text-[var(--color-bone)]'}>
          <HeroNumeral value={value} unit={unit} />
        </div>
      </div>
      <div className="mt-3 text-[11.5px] text-[var(--color-ash)] font-medium leading-none">{sub}</div>
    </div>
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
    ok:   { dot: 'bg-[var(--color-patina)]',  label: '完成' },
    warn: { dot: 'bg-[var(--color-ember)]',   label: '部分' },
    err:  { dot: 'bg-[var(--color-iron)]',    label: '失败' },
  };
  const s = statusMap[status];
  return (
    <div className="grid grid-cols-[60px_1fr_auto] gap-4 py-3.5 border-b border-[var(--color-hairline-faint)] last:border-b-0 items-baseline hover:bg-[rgba(255,255,255,0.015)] rounded-lg transition-colors -mx-3 px-3 cursor-pointer">
      <span className="font-mono text-[11px] text-[var(--color-smoke)] tabular">{when}</span>
      <div className="min-w-0">
        <div className="flex items-baseline gap-2.5">
          <span className="text-[14px] text-[var(--color-bone)] font-medium">{kind}</span>
          <span className="text-[12.5px] text-[var(--color-ash)] truncate">{title}</span>
        </div>
      </div>
      <span className="flex items-center gap-2 text-[11px] text-[var(--color-ash)] flex-shrink-0">
        <span className={`status-dot ${s.dot}`} />
        {s.label}
      </span>
    </div>
  );
}

export function ActionRow({
  label,
  kbd,
  onClick,
}: {
  label: string;
  kbd?: string;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left py-4 border-b border-[var(--color-hairline-faint)] last:border-b-0 group transition-colors hover:bg-[rgba(255,255,255,0.015)] rounded-lg -mx-3 px-3 flex items-baseline justify-between"
    >
      <span className="text-[14.5px] text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors font-medium">
        {label}
      </span>
      {kbd && <span className="mono-cap">{kbd}</span>}
    </button>
  );
}
