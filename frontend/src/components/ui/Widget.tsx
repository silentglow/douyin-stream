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
  blue: 'bg-gradient-to-br from-white to-[rgba(10,132,255,0.06)]',
  green: 'bg-gradient-to-br from-white to-[rgba(48,209,88,0.06)]',
  red: 'bg-gradient-to-br from-white to-[rgba(255,69,58,0.06)]',
  purple: 'bg-gradient-to-br from-white to-[rgba(175,82,222,0.06)]',
  orange: 'bg-gradient-to-br from-white to-[rgba(255,159,10,0.06)]',
  teal: 'bg-gradient-to-br from-white to-[rgba(90,200,250,0.06)]',
  none: '',
};

const sizeClass = {
  small: 'col-span-1',
  medium: 'col-span-2',
  large: 'col-span-2 sm:col-span-3 lg:col-span-4',
};

const minHeightClass = {
  small: 'min-h-[140px]',
  medium: 'min-h-[160px]',
  large: 'min-h-[180px]',
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
    <div
      onClick={onClick}
      className={cn(
        'bg-white dark:bg-[#1C1C1E] rounded-[22px]',
        'shadow-[0_2px_12px_rgba(0,0,0,0.06),0_0_1px_rgba(0,0,0,0.04)]',
        'dark:shadow-[0_2px_12px_rgba(0,0,0,0.3),0_0_1px_rgba(255,255,255,0.04)]',
        'p-5 flex flex-col gap-3 relative overflow-hidden',
        'cursor-pointer transition-all duration-200',
        'hover:shadow-[0_4px_20px_rgba(0,0,0,0.1)]',
        'hover:scale-[0.98]',
        sizeClass[size],
        minHeightClass[size],
        tintMap[tint],
        className,
      )}
    >
      <div className="flex items-center gap-2">
        {icon && (
          <div className={cn('w-6 h-6 rounded-lg flex items-center justify-center text-sm shrink-0', iconBg)}>
            {icon}
          </div>
        )}
        <span className="text-[17px] font-semibold text-[#8E8E93]">
          {title}
        </span>
      </div>
      <div className="flex-1 flex flex-col justify-center min-w-0">
        {children}
      </div>
      {footer && (
        <div className="text-xs text-[#8E8E93]">{footer}</div>
      )}
    </div>
  );
}
