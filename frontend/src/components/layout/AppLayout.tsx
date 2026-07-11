import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import {
  Search,
  FolderOpen,
  Settings,
  Sun,
  Moon,
  Monitor,
  ListTodo,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { TaskIsland } from '@/components/layout/TaskIsland';
import { useTheme } from 'next-themes';
import { cn } from '@/lib/utils';

/* 内容库干活 · 设置配置。任务：右下角状态球。阅读：创作者详情内打开。 */
const navItems = [
  {
    to: '/library',
    idx: '01',
    icon: FolderOpen,
    label: '内容库',
    en: 'library',
    kbd: '⌘1',
  },
  {
    to: '/settings',
    idx: '02',
    icon: Settings,
    label: '系统设置',
    en: 'settings',
    kbd: '⌘2',
  },
];

interface CommandPaletteProps {
  open: boolean;
  setOpen: (open: boolean) => void;
  setTaskDrawerOpen: (open: boolean) => void;
}

function CommandPalette({ open, setOpen, setTaskDrawerOpen }: CommandPaletteProps) {
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(!open);
      }
      // ⌘` 打开任务中心
      if ((e.metaKey || e.ctrlKey) && e.key === '`') {
        e.preventDefault();
        setOpen(false);
        setTaskDrawerOpen(true);
      }
      // ⌘1 .. ⌘2 导航
      if ((e.metaKey || e.ctrlKey) && e.key >= '1' && e.key <= '2') {
        const idx = parseInt(e.key, 10) - 1;
        if (idx < navItems.length) {
          e.preventDefault();
          navigate(navItems[idx].to);
          setOpen(false);
          setTaskDrawerOpen(false);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [navigate, open, setOpen, setTaskDrawerOpen]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[16vh]">
      <div className="absolute inset-0 bg-black/10 backdrop-blur-md" onClick={() => setOpen(false)} />
      <div className="relative w-full max-w-lg bg-[rgba(255,255,255,0.9)] dark:bg-[rgba(28,28,30,0.92)] backdrop-blur-2xl border border-black/5 dark:border-white/10 rounded-2xl shadow-[0_24px_64px_rgba(0,0,0,0.15)] overflow-hidden bloom-enter">
        <div className="px-6 pt-5 pb-3 border-b border-[var(--color-hairline-faint)]">
          <div className="flex items-baseline justify-between mb-3">
            <span className="eyebrow">Command</span>
            <span className="mono-cap">esc</span>
          </div>
          <div className="flex items-center gap-3">
            <Search className="w-4 h-4 text-[var(--color-smoke)]" strokeWidth={2} />
            <input
              type="text"
              placeholder="跳转页面或打开任务中心…"
              className="flex-1 bg-transparent font-sans text-[18px] font-medium text-[var(--color-bone)] placeholder:text-[var(--color-smoke)] outline-none"
              autoFocus
            />
          </div>
        </div>

        <div className="max-h-[360px] overflow-y-auto py-2">
          <div className="px-6 pt-3 pb-1.5 eyebrow">页面</div>
          {navItems.map((item) => (
            <button
              key={item.to}
              type="button"
              className="w-full px-6 py-3 flex items-center gap-5 hover:bg-[rgba(0,0,0,0.04)] dark:hover:bg-white/[0.04] rounded-lg transition-colors group cursor-pointer"
              onClick={() => {
                navigate(item.to);
                setTaskDrawerOpen(false);
                setOpen(false);
              }}
            >
              <span className="mono-cap w-8 flex-shrink-0">{item.idx}</span>
              <span className="text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors flex-shrink-0">
                <item.icon className="w-4 h-4" />
              </span>
              <span className="text-[13px] text-[var(--color-ash)] flex-1 text-left">{item.label}</span>
              <kbd className="mono-cap">{item.kbd}</kbd>
            </button>
          ))}

          <div className="px-6 pt-3 pb-1.5 eyebrow">任务</div>
          <button
            type="button"
            className="w-full px-6 py-3 flex items-center gap-5 hover:bg-[rgba(0,0,0,0.04)] dark:hover:bg-white/[0.04] rounded-lg transition-colors group cursor-pointer"
            onClick={() => {
              setTaskDrawerOpen(true);
              setOpen(false);
            }}
          >
            <span className="mono-cap w-8 flex-shrink-0">T</span>
            <span className="text-[var(--color-bone)] group-hover:text-[var(--color-rust)] transition-colors flex-shrink-0">
              <ListTodo className="w-4 h-4" />
            </span>
            <span className="text-[13px] text-[var(--color-ash)] flex-1 text-left">打开任务</span>
            <kbd className="mono-cap">⌘`</kbd>
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [now, setNow] = useState(new Date());
  const [taskDrawerOpen, setTaskDrawerOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => window.localStorage.getItem('media-tools:sidebar-collapsed') === '1',
  );
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  // 兼容旧书签 /tasks → /library?tasks=1：进内容库并打开任务中心
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get('tasks') === '1') {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- open panel from deep link
      setTaskDrawerOpen(true);
      params.delete('tasks');
      const next = params.toString();
      navigate({ pathname: location.pathname, search: next ? `?${next}` : '' }, { replace: true });
    }
  }, [location.pathname, location.search, navigate]);

  const toggleSidebar = () => {
    setSidebarCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem('media-tools:sidebar-collapsed', next ? '1' : '0');
      return next;
    });
  };

  const timeStr = now.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  return (
    <div className="flex h-screen bg-[var(--color-ink)] overflow-hidden">
      {/* LEFT SIDEBAR */}
      <nav
        className={cn(
          'flex-shrink-0 border-r border-[var(--color-hairline)] bg-[var(--sidebar)] backdrop-blur-xl flex flex-col z-20 transition-[width] duration-200',
          sidebarCollapsed ? 'w-[68px]' : 'w-[220px]',
        )}
      >
        <NavLink
          to="/library"
          onClick={() => setTaskDrawerOpen(false)}
          className={cn(
            'h-16 flex items-center border-b border-[var(--color-hairline)] group hover:bg-black/[0.01] dark:hover:bg-white/[0.01] transition-colors',
            sidebarCollapsed ? 'justify-center px-3' : 'justify-between px-4',
          )}
          title="内容库"
        >
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 rounded-lg overflow-hidden flex items-center justify-center transition-all duration-300 shadow-sm border border-[var(--color-hairline-strong)] group-hover:scale-105 group-hover:shadow-md">
              <img src="/logo.png" alt="Media Studio Logo" className="w-full h-full object-cover" />
            </div>
            {!sidebarCollapsed && (
              <span className="font-display text-[15px] font-bold text-[var(--color-bone)] truncate tracking-wide">
                Media Studio
              </span>
            )}
          </div>
          <span className={cn('relative w-2 h-2 shrink-0', sidebarCollapsed ? 'hidden' : 'flex')}>
            <span className="absolute inset-0 rounded-full bg-[var(--color-patina)] animate-ping opacity-75" />
            <span className="relative rounded-full w-2 h-2 bg-[var(--color-patina)]" />
          </span>
        </NavLink>

        <div
          className={cn(
            'flex-1 flex flex-col py-4 space-y-1 stagger overflow-y-auto',
            sidebarCollapsed ? 'px-2' : 'px-3',
          )}
        >
          {navItems.map((item) => {
            const isActive =
              location.pathname === item.to ||
              location.pathname.startsWith(`${item.to}/`) ||
              (item.to === '/library' && location.pathname === '/');
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setTaskDrawerOpen(false)}
                title={`${item.label} (${item.kbd})`}
                className={`relative flex items-center rounded-xl ui-press group ${sidebarCollapsed ? 'justify-center px-2 py-3' : 'justify-between px-3 py-2.5'} ${
                  isActive
                    ? 'bg-black/[0.04] dark:bg-white/[0.05] text-[var(--color-rust)] font-semibold shadow-sm border border-black/[0.02] dark:border-white/[0.02]'
                    : 'text-[var(--color-ash)] hover:text-[var(--color-bone)] hover:bg-black/[0.02] dark:hover:bg-white/[0.02]'
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <item.icon
                    className={`w-[18px] h-[18px] transition-colors stroke-[1.8] ${
                      isActive
                        ? 'text-[var(--color-rust)]'
                        : 'text-[var(--color-smoke)] group-hover:text-[var(--color-bone)]'
                    }`}
                  />
                  {!sidebarCollapsed && <span className="text-[13.5px] truncate">{item.label}</span>}
                </div>
                {!sidebarCollapsed && (
                  <kbd className="mono-cap text-[9px] px-1.5 py-0.5 rounded bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.02] dark:border-white/[0.02] opacity-60 group-hover:opacity-100 transition-opacity">
                    {item.kbd.replace('⌘', '')}
                  </kbd>
                )}
              </NavLink>
            );
          })}
        </div>

        <div
          className={cn(
            'border-t border-[var(--color-hairline)] flex flex-col gap-3 bg-black/[0.005] dark:bg-white/[0.002]',
            sidebarCollapsed ? 'p-2' : 'p-3',
          )}
        >
          {!sidebarCollapsed && (
            <>
              <div className="flex items-center gap-0.5 p-0.5 bg-black/[0.03] dark:bg-white/[0.04] rounded-lg border border-black/[0.03] dark:border-white/[0.04] shrink-0">
                {[
                  { value: 'light', label: '浅色模式', Icon: Sun },
                  { value: 'dark', label: '深色模式', Icon: Moon },
                  { value: 'system', label: '跟随系统', Icon: Monitor },
                ].map(({ value, label, Icon }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setTheme(value)}
                    title={label}
                    className={cn(
                      'flex-1 py-1.5 rounded-md flex justify-center items-center transition-all',
                      theme === value
                        ? 'bg-white dark:bg-[var(--color-paper)] text-[var(--color-rust)] shadow-sm font-semibold'
                        : 'text-[var(--color-ash)] hover:text-[var(--color-bone)]',
                    )}
                  >
                    <Icon className="w-3.5 h-3.5" />
                  </button>
                ))}
              </div>
              <div className="flex items-center justify-between text-xs text-[var(--color-smoke)] px-1 select-none font-mono">
                <span>CLOCK</span>
                <span className="tabular-nums font-semibold text-[var(--color-ash)]">{timeStr}</span>
              </div>
            </>
          )}
          <button
            type="button"
            onClick={toggleSidebar}
            className="ui-press h-9 rounded-lg flex items-center justify-center gap-2 text-[var(--color-smoke)] hover:text-[var(--color-bone)] hover:bg-black/[0.04] dark:hover:bg-white/[0.05]"
            title={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
          >
            {sidebarCollapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
            {!sidebarCollapsed && <span className="text-[11px]">收起侧栏</span>}
          </button>
        </div>
      </nav>

      <main className="flex-1 overflow-hidden flex flex-col relative">
        <div className="flex-1 overflow-hidden relative">
          <Outlet context={{ setTaskDrawerOpen }} />
        </div>
      </main>

      <CommandPalette open={cmdOpen} setOpen={setCmdOpen} setTaskDrawerOpen={setTaskDrawerOpen} />
      <TaskIsland
        isOpen={taskDrawerOpen}
        onToggle={() => setTaskDrawerOpen(!taskDrawerOpen)}
        onClose={() => setTaskDrawerOpen(false)}
      />
    </div>
  );
}
