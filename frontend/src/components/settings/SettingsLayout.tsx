import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { cn } from '@/lib/utils';

export function SettingsGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <div className="text-[11px] font-semibold text-fg-muted uppercase tracking-wider mb-3">
        {title}
      </div>
      <div className="bg-surface rounded-xl border border-border-subtle overflow-hidden divide-y divide-border-subtle">
        {children}
      </div>
    </div>
  );
}

interface SettingsItemProps {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  value?: React.ReactNode;
  onClick?: () => void;
  children?: React.ReactNode;
}

export function SettingsItem({
  icon,
  iconBg,
  label,
  value,
  onClick,
  children,
}: SettingsItemProps) {
  const hasChildren = !!children;
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div>
      <div
        onClick={() => {
          if (hasChildren) setIsExpanded(!isExpanded);
          else if (onClick) onClick();
        }}
        className={cn(
          "flex items-center justify-between px-5 py-4 cursor-pointer transition-colors hover:bg-black/[0.02]",
          !hasChildren && !onClick && "cursor-default hover:bg-transparent"
        )}
      >
        <div className="flex items-center gap-3">
          <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center", iconBg)}>
            {icon}
          </div>
          <span className="text-sm text-fg-primary">{label}</span>
        </div>
        <div className="flex items-center gap-2">
          {value !== undefined && (
            <span className="text-xs text-fg-muted font-mono">{value}</span>
          )}
          {hasChildren && (
            <ChevronRight className={cn("w-4 h-4 text-fg-muted transition-transform", isExpanded && "rotate-90")} />
          )}
          {onClick && !hasChildren && (
            <ChevronRight className="w-4 h-4 text-fg-muted" />
          )}
        </div>
      </div>
      <AnimatePresence>
        {hasChildren && isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 border-t border-border-subtle">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
