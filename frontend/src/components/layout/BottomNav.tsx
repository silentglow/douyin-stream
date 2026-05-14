import { NavLink, useLocation } from 'react-router-dom';
import { LayoutGrid, Library, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';

interface BottomNavProps {
  taskCount?: number;
}

function NavItem({
  icon: Icon,
  label,
  href,
  badge,
}: {
  icon: typeof LayoutGrid;
  label: string;
  href: string;
  badge?: number;
}) {
  const location = useLocation();
  const isActive = location.pathname === href;

  return (
    <NavLink
      to={href}
      className={cn(
        "flex flex-col items-center justify-center gap-0.5 py-2 px-4 min-w-[64px]",
        "transition-colors duration-200",
        isActive ? "text-primary" : "text-muted-foreground"
      )}
    >
      <div className="relative">
        <Icon
          className={cn(
            "size-[22px] transition-all duration-200",
            isActive ? "stroke-[2.5px]" : "stroke-[1.5px]"
          )}
        />
        {badge != null && badge > 0 && (
          <span className="absolute -top-1 -right-2 min-w-[16px] h-[16px] rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center px-1">
            {badge > 99 ? '99+' : badge}
          </span>
        )}
      </div>
      <span className={cn(
        "text-[10px] font-medium",
        isActive ? "text-primary" : "text-muted-foreground"
      )}>
        {label}
      </span>
    </NavLink>
  );
}

export default function BottomNav({ taskCount = 0 }: BottomNavProps) {
  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 h-16 flex items-center justify-around border-t border-border/40 apple-glass-bar pb-[env(safe-area-inset-bottom,0px)]">
      <NavItem icon={LayoutGrid} label="工作台" href="/home" />
      <NavItem icon={Library} label="内容库" href="/library" />
      <NavItem
        icon={Settings}
        label="设置"
        href="/settings"
        badge={taskCount > 0 ? taskCount : undefined}
      />
    </nav>
  );
}
