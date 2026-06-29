import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useStore } from '@/store/useStore';
import { useEffect, useState } from 'react';
import { getTaskDisplayState } from '@/lib/task-utils';
import type { Task } from '@/lib/api';
import { Search, Home, FolderOpen, FileText, Settings, Sun, Moon, Monitor } from 'lucide-react';
import { TaskIsland } from '@/components/layout/TaskIsland';
import { useTheme } from 'next-themes';


/* ═══════════════════════════════════════════════════════════════
 *  Navigation — typographic rail.
 *  Each item uses a dedicated Lucide icon and clear label.
 * ═══════════════════════════════════════════════════════════════ */
const navItems = [
  { to: '/home',        idx: '01', icon: Home,          label: '工作台',     en: 'studio',     kbd: '⌘1' },
  { to: '/library',     idx: '02', icon: FolderOpen,    label: '内容库',     en: 'library',    kbd: '⌘2' },
  { to: '/transcripts', idx: '03', icon: FileText,      label: '文稿库',     en: 'transcripts',kbd: '⌘3' },
  { to: '/settings',    idx: '04', icon: Settings,      label: '系统设置',   en: 'settings',   kbd: '⌘4' },
];

/* ═══════════════════════════════════════════════════════════════
 *  Live task ticker — runs along the top of the app when active.
 *  Inspired by a Reuters/Bloomberg terminal strip, restrained.
 * ═══════════════════════════════════════════════════════════════ */
function GlobalTicker({ onOpenDrawer }: { onOpenDrawer: () => void }) {
  const tasks = useStore((s) => s.tasks);

  const activeTasks = tasks.filter((t) => {
    const s = getTaskDisplayState(t);
    return s === 'running' || s === 'paused';
  });

  if (activeTasks.length === 0) return null;

  return (
    <div className="flex-shrink-0 border-b border-[var(--color-hairline-faint)] bg-[var(--color-paper)]/60 backdrop-blur-xl">
      <div className="flex items-center h-10">
        {/* Label */}
        <div className="flex items-center gap-2.5 pl-6 pr-5 h-full border-r border-[var(--color-hairline-faint)] flex-shrink-0">
          <span className="relative inline-block w-2 h-2">
            <span className="absolute inset-0 rounded-full bg-[var(--color-rust)] pulse-dot" />
            <span className="absolute inset-0 rounded-full bg-[var(--color-rust)] pulse-ring" />
          </span>
          <span className="text-[12px] font-medium text-[var(--color-ash)]">
            <span className="font-bold text-[15px] text-[var(--color-rust)] mr-1.5">{activeTasks.length}</span>
            运行中
          </span>
        </div>

        {/* Task strip */}
        <div className="flex-1 min-w-0 px-5 flex items-center gap-7 overflow-hidden">
          {activeTasks.slice(0, 4).map((task) => (
            <TickerItem key={task.task_id} task={task} />
          ))}
        </div>

        {/* CTA */}
        <button
          onClick={onOpenDrawer}
          className="flex items-center gap-1.5 px-6 h-full border-l border-[var(--color-hairline-faint)] eyebrow hover:text-[var(--color-rust)] transition-colors flex-shrink-0 cursor-pointer"
        >
          全部 →
        </button>
      </div>
    </div>
  );
}

function TickerItem({ task }: { task: Task }) {
  const pct = Math.round((task.progress || 0) * 100);
  const label =
    (() => {
      try {
        const p = JSON.parse(task.payload || '{}');
        return p.msg || '';
      } catch { return ''; }
    })() ||
    (task.task_type === 'creator_sync_full' ? '创作者同步'
      : task.task_type === 'pipeline' ? '下载并转写'
      : task.task_type === 'transcribe' ? '转写'
      : task.task_type || '任务');

  return (
    <div className="flex items-center gap-3 min-w-0 flex-1 max-w-[320px]">
      <span className="font-mono text-[10px] text-[var(--color-smoke)] flex-shrink-0">
        #{(task.task_id || '').slice(0, 6)}
      </span>
      <span className="text-[12px] text-[var(--color-ash)] truncate flex-1">
        {label}
      </span>
      <span className="font-sans font-semibold text-[13px] text-[var(--color-rust)] tabular flex-shrink-0">
        {pct}<span className="text-[10px]">%</span>
      </span>
      <div className="hidden md:block w-16 h-1 bg-[var(--color-hairline-strong)] rounded-full relative overflow-hidden flex-shrink-0">
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundImage: 'linear-gradient(90deg, #0071e3 0%, #005bb5 100%)' }}
        />
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
 *  Command palette — editorial flavor, sharp edges
 * ═══════════════════════════════════════════════════════════════ */
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
      // 任务面板单独绑 ⌘` (反引号)，与导航 ⌘1-⌘5 解耦——避免视觉位次错位
      if ((e.metaKey || e.ctrlKey) && e.key === '`') {
        e.preventDefault();
        setOpen(false);
        setTaskDrawerOpen(true);
      }
      // ⌘1 .. ⌘4 = 导航到对应 navItems
      if ((e.metaKey || e.ctrlKey) && e.key >= '1' && e.key <= '4') {
        const idx = parseInt(e.key) - 1;
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
      <div className="relative w-full max-w-lg bg-[rgba(255,255,255,0.85)] backdrop-blur-2xl border border-black/5 rounded-2xl shadow-[0_24px_64px_rgba(0,0,0,0.15)] overflow-hidden bloom-enter">
        {/* Header */}
        <div className="px-6 pt-5 pb-3 border-b border-[var(--color-hairline-faint)]">
          <div className="flex items-baseline justify-between mb-3">
            <span className="eyebrow">Command</span>
            <span className="mono-cap">esc</span>
          </div>
          <div className="flex items-center gap-3">
            <Search className="w-4 h-4 text-[var(--color-smoke)]" strokeWidth={2} />
            <input
              type="text"
              placeholder="键入命令、跳转或查询⋯"
              className="flex-1 bg-transparent font-sans text-[20px] font-medium text-[var(--color-bone)] placeholder:text-[var(--color-smoke)] outline-none"
              autoFocus
            />
          </div>
        </div>

        {/* Items */}
        <div className="max-h-[360px] overflow-y-auto py-2">
          <div className="px-6 pt-3 pb-1.5 eyebrow">Navigate</div>
          {navItems.map((item) => (
            <button
              key={item.to}
              className="w-full px-6 py-3 flex items-center gap-5 hover:bg-[rgba(0,0,0,0.04)] rounded-lg transition-colors group cursor-pointer"
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
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
 *  AppLayout — the masthead frame
 * ═══════════════════════════════════════════════════════════════ */
export default function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [now, setNow] = useState(new Date());
  const [taskDrawerOpen, setTaskDrawerOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  // /tasks 路由已删除，任务面板现在只通过 island drawer 呈现；以下兼容老书签/老地址
  useEffect(() => {
    if (location.pathname === '/tasks') {
      navigate('/home', { replace: true });
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional: open drawer on old route redirect
      setTaskDrawerOpen(true);
    }
  }, [location.pathname, navigate]);

  const timeStr = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });

  return (
    <div className="flex h-screen bg-[var(--color-ink)] overflow-hidden">
      {/* ═══ LEFT SIDEBAR ═══════════════════════════════════════════ */}
      <nav className="w-[240px] flex-shrink-0 border-r border-[var(--color-hairline)] bg-[var(--sidebar)] backdrop-blur-xl flex flex-col z-20">
        {/* Header / Workspace brand */}
        <NavLink
          to="/home"
          onClick={() => setTaskDrawerOpen(false)}
          className="h-16 px-5 flex items-center justify-between border-b border-[var(--color-hairline)] group hover:bg-black/[0.01] dark:hover:bg-white/[0.01] transition-colors"
          title="工作台"
        >
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 rounded-lg overflow-hidden flex items-center justify-center transition-all duration-300 shadow-sm border border-[var(--color-hairline-strong)] group-hover:scale-105 group-hover:shadow-md">
              <img src="/logo.png" alt="Media Studio Logo" className="w-full h-full object-cover" />
            </div>
            <span className="font-display text-[15px] font-bold text-[var(--color-bone)] truncate tracking-wide">
              Media Studio
            </span>
          </div>
          <span className="relative flex w-2 h-2 shrink-0">
            <span className="absolute inset-0 rounded-full bg-[var(--color-patina)] animate-ping opacity-75" />
            <span className="relative rounded-full w-2 h-2 bg-[var(--color-patina)]" />
          </span>
        </NavLink>

        {/* Nav Links */}
        <div className="flex-1 flex flex-col py-4 px-3 space-y-1 stagger overflow-y-auto">
          {navItems.map((item) => {
            const isActive = location.pathname.startsWith(item.to)
              || (item.to === '/home' && location.pathname === '/');
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setTaskDrawerOpen(false)}
                title={`${item.label} (${item.kbd})`}
                className={`relative flex items-center justify-between px-3 py-2.5 rounded-xl transition-all duration-200 group ${
                  isActive
                    ? 'bg-black/[0.04] dark:bg-white/[0.05] text-[var(--color-rust)] font-semibold shadow-sm border border-black/[0.02] dark:border-white/[0.02]'
                    : 'text-[var(--color-ash)] hover:text-[var(--color-bone)] hover:bg-black/[0.02] dark:hover:bg-white/[0.02]'
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <item.icon className={`w-[18px] h-[18px] transition-colors stroke-[1.8] ${isActive ? 'text-[var(--color-rust)]' : 'text-[var(--color-smoke)] group-hover:text-[var(--color-bone)]'}`} />
                  <span className="text-[13.5px] truncate">
                    {item.label}
                  </span>
                </div>
                <kbd className="mono-cap text-[9px] px-1.5 py-0.5 rounded bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.02] dark:border-white/[0.02] opacity-60 group-hover:opacity-100 transition-opacity">
                  {item.kbd.replace('⌘', '')}
                </kbd>
              </NavLink>
            );
          })}
        </div>

        {/* Footer — Theme switcher & minimal clock */}
        <div className="border-t border-[var(--color-hairline)] p-4 flex flex-col gap-3 bg-black/[0.005] dark:bg-white/[0.002]">
          {/* Theme switcher button group */}
          <div className="flex items-center gap-0.5 p-0.5 bg-black/[0.03] dark:bg-white/[0.04] rounded-lg border border-black/[0.03] dark:border-white/[0.04] shrink-0">
            <button
              onClick={() => setTheme('light')}
              title="浅色模式"
              className={`flex-1 py-1.5 rounded-md flex justify-center items-center transition-all ${
                theme === 'light'
                  ? 'bg-white dark:bg-[var(--color-paper)] text-[var(--color-rust)] shadow-sm font-semibold'
                  : 'text-[var(--color-ash)] hover:text-[var(--color-bone)]'
              }`}
            >
              <Sun className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setTheme('dark')}
              title="深色模式"
              className={`flex-1 py-1.5 rounded-md flex justify-center items-center transition-all ${
                theme === 'dark'
                  ? 'bg-white dark:bg-[var(--color-paper)] text-[var(--color-rust)] shadow-sm font-semibold'
                  : 'text-[var(--color-ash)] hover:text-[var(--color-bone)]'
              }`}
            >
              <Moon className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setTheme('system')}
              title="跟随系统"
              className={`flex-1 py-1.5 rounded-md flex justify-center items-center transition-all ${
                theme === 'system'
                  ? 'bg-white dark:bg-[var(--color-paper)] text-[var(--color-rust)] shadow-sm font-semibold'
                  : 'text-[var(--color-ash)] hover:text-[var(--color-bone)]'
              }`}
            >
              <Monitor className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="flex items-center justify-between text-xs text-[var(--color-smoke)] px-1 select-none font-mono">
            <span>CLOCK</span>
            <span className="tabular-nums font-semibold text-[var(--color-ash)]">{timeStr}</span>
          </div>
        </div>
      </nav>

      {/* ═══ MAIN ════════════════════════════════════════════════ */}
      <main className="flex-1 overflow-hidden flex flex-col relative">
        <GlobalTicker onOpenDrawer={() => setTaskDrawerOpen(true)} />

        {/* Page */}
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
