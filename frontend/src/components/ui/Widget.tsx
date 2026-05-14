import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import { type ReactNode } from 'react';

export type WidgetSize = 'small' | 'medium' | 'large';

interface WidgetProps {
  size?: WidgetSize;
  icon?: ReactNode;
  iconBg?: string;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  tint?: 'blue' | 'green' | 'red' | 'purple' | 'orange' | 'teal' | 'none';
  onClick?: () => void;
}

const tintMap = {
  blue: 'bg-gradient-to-br from-card to-[rgba(10,132,255,0.06)]',
  green: 'bg-gradient-to-br from-card to-[rgba(48,209,88,0.06)]',
  red: 'bg-gradient-to-br from-card to-[rgba(255,69,58,0.06)]',
  purple: 'bg-gradient-to-br from-card to-[rgba(175,82,222,0.06)]',
  orange: 'bg-gradient-to-br from-card to-[rgba(255,159,10,0.06)]',
  teal: 'bg-gradient-to-br from-card to-[rgba(90,200,250,0.06)]',
  none: '',
};

const sizeClass = {
  small: 'col-span-1',
  medium: 'col-span-2',
  large: 'col-span-2 sm:col-span-3 lg:col-span-4',
};

const aspectClass = {
  small: 'aspect-square',
  medium: 'aspect-[2/1]',
  large: 'aspect-[2/1] lg:aspect-[4/2]',
};

export function Widget({
  size = 'small',
  icon,
  iconBg,
  title,
  children,
  footer,
  className,
  tint = 'none',
  onClick,
}: WidgetProps) {
  return (
    <motion.div
      onClick={onClick}
      whileHover={{ scale: 0.98 }}
      whileTap={{ scale: 0.97 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      className={cn(
        'bg-card',
        'apple-shadow-widget',
        'p-5 max-sm:p-4 flex flex-col gap-3 relative overflow-hidden',
        'rounded-[22px] max-sm:rounded-[18px]',
        'cursor-pointer',
        sizeClass[size],
        aspectClass[size],
        tintMap[tint],
        className,
      )}
    >
      <div className="flex items-center gap-2">
        {icon && (
          <div className={cn('w-7 h-7 rounded-lg flex items-center justify-center text-sm shrink-0', iconBg)}>
            {icon}
          </div>
        )}
        <span className="text-[15px] font-semibold text-[#8E8E93]">
          {title}
        </span>
      </div>
      <div className="flex-1 flex flex-col justify-center min-w-0">
        {children}
      </div>
      {footer && (
        <div className="text-xs text-[#8E8E93]">{footer}</div>
      )}
    </motion.div>
  );
}
