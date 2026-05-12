import { NavLink } from 'react-router-dom';
import { Compass, Users, Settings, Sun, Moon, X, LayoutDashboard } from 'lucide-react';
import { useTheme } from 'next-themes';
import { cn } from '@/lib/utils';
import { TaskMonitorPanel } from '@/components/layout/TaskMonitorPanel';

interface SidebarProps {
  listContent?: React.ReactNode;
  open?: boolean;
  onClose?: () => void;
}

function SidebarItem({
  icon: Icon,
  label,
  href,
  badge,
}: {
  icon: typeof Compass;
  label: string;
  href: string;
  badge?: number;
}) {
  return (
    <NavLink
      to={href}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center gap-3 h-10 px-3 rounded-[8px] cursor-pointer select-none",
          "transition-all duration-200 spring-ease-subtle",
          isActive
            ? "bg-primary/12 text-primary font-semibold"
            : "hover:bg-secondary text-foreground font-medium",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        )
      }
    >
      {({ isActive }) => (
        <>
          <div className={cn(
            "relative",
            isActive && "apple-active-glow"
          )}>
            <Icon
              className={cn(
                "size-5 shrink-0 transition-colors duration-200",
                isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
              )}
            />
          </div>
          <span className="text-body">{label}</span>
          {badge != null && badge > 0 && (
            <span className="ml-auto min-w-[18px] h-[18px] rounded-[9px] bg-destructive text-destructive-foreground text-[11px] font-semibold flex items-center justify-center px-1.5">
              {badge > 99 ? '99+' : badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const isDark = theme === 'dark';
  const toggle = () => setTheme(isDark ? 'light' : 'dark');
  return (
    <button
      onClick={toggle}
      className="group flex items-center gap-3 h-10 px-3 rounded-[8px] cursor-pointer select-none transition-all duration-200 spring-ease-subtle hover:bg-secondary text-foreground font-medium w-full"
      aria-label={`当前主题: ${isDark ? '深色' : '浅色'}，点击切换`}
    >
      {isDark ? <Moon className="size-5 text-muted-foreground group-hover:text-foreground" /> : <Sun className="size-5 text-muted-foreground group-hover:text-foreground" />}
      <span className="text-body">主题 · {isDark ? '深色' : '浅色'}</span>
    </button>
  );
}

export default function Sidebar({ listContent, open, onClose }: SidebarProps) {
  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside className={cn(
        'w-[260px] h-full overflow-y-auto flex-shrink-0 flex flex-col apple-glass-sidebar border-r border-sidebar-border',
        'fixed inset-y-0 left-0 z-50 transform transition-transform duration-300 ease-apple-spring lg:relative lg:translate-x-0',
        open ? 'translate-x-0' : '-translate-x-full'
      )}>
        {/* Close button for mobile */}
        <button
          className="absolute top-3 right-3 lg:hidden flex items-center justify-center size-8 rounded-[var(--radius-button)] hover:bg-secondary transition-colors"
          onClick={onClose}
          aria-label="关闭侧边栏"
        >
          <X className="size-4 text-muted-foreground" />
        </button>
      {/* Header */}
      <div className="shrink-0 h-14 px-5 flex items-center">
        <div className="w-8 h-8 rounded-[10px] bg-gradient-to-br from-primary to-primary/70 flex items-center justify-center">
          <span className="text-white font-bold text-sm">M</span>
        </div>
        <h1 className="ml-3 text-title-3 font-semibold text-sidebar-foreground tracking-tight">Media Tools</h1>
      </div>

      {/* Primary Nav */}
      <nav className="px-3 py-2 space-y-0.5">
        <SidebarItem icon={Compass} label="发现" href="/discover" />
        <SidebarItem icon={Users} label="创作者" href="/creators" />
        <SidebarItem icon={LayoutDashboard} label="仪表盘" href="/dashboard" />
        <SidebarItem icon={Settings} label="设置" href="/settings" />
      </nav>

      {/* Divider */}
      <div className="mx-3 my-3 h-px bg-sidebar-border" />

      {/* Theme Toggle */}
      <div className="px-3">
        <ThemeToggle />
      </div>

      {/* Divider */}
      <div className="mx-3 my-3 h-px bg-sidebar-border" />

      {/* Contextual List */}
      <div className="px-3 py-1 space-y-1 flex-1">
        <TaskMonitorPanel />
        {listContent && (
          <div className="px-3 mt-4 mb-2 text-small font-semibold text-muted-foreground uppercase tracking-wide">
            关注创作者
          </div>
        )}
        {listContent}
      </div>
    </aside>
    </>
  );
}
