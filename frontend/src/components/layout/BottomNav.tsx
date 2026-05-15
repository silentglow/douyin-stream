import { NavLink, useLocation } from 'react-router-dom';
import { LayoutGrid, Library, Settings, Search, Compass, Activity } from 'lucide-react';
import { cn } from '@/lib/utils';

interface BottomNavProps {
  taskCount?: number;
  onOpenSearch?: () => void;
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
        "transition-colors duration-200 spring-ease-subtle active:scale-[0.92]",
        isActive ? "text-primary" : "text-muted-foreground"
      )}
    >
      <div className="relative">
        <Icon
          className={cn(
            "size-[22px] transition-all duration-200 spring-ease-subtle",
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

export default function BottomNav({ taskCount = 0, onOpenSearch }: BottomNavProps) {
  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 h-16 flex items-center justify-around border-t border-border/40 apple-glass-bar pb-[env(safe-area-inset-bottom,0px)]">
      <NavItem icon={LayoutGrid} label="工作台" href="/home" />
      <NavItem icon={Compass} label="发现" href="/discover" />
      <button
        onClick={onOpenSearch}
        className="flex flex-col items-center justify-center gap-0.5 py-2 px-4 min-w-[64px] text-muted-foreground hover:text-primary transition-colors spring-ease-subtle active:scale-[0.92]"
      >
        <Search className="size-[22px] stroke-[1.5px]" />
        <span className="text-[10px] font-medium">搜索</span>
      </button>
      <NavItem icon={Library} label="内容库" href="/library" />
      <NavItem
        icon={Activity}
        label="任务"
        href="/tasks"
        badge={taskCount > 0 ? taskCount : undefined}
      />
      <NavItem icon={Settings} label="设置" href="/settings" />
    </nav>
  );
}
