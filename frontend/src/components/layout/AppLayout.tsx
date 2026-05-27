import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useStore } from '@/store/useStore';
import { useEffect, useState } from 'react';
import { getTaskDisplayState } from '@/lib/task-utils';
import type { Task } from '@/lib/api';
import { Search, Home, FolderOpen, FileText, Compass, Settings } from 'lucide-react';
import { TaskIsland } from '@/components/layout/TaskIsland';


/* ═══════════════════════════════════════════════════════════════
 *  Navigation — typographic rail.
 *  Each item uses a dedicated Lucide icon and clear label.
 * ═══════════════════════════════════════════════════════════════ */
const navItems = [
  { to: '/home',        idx: '01', icon: Home,          label: 'Studio',     en: 'studio',     kbd: '⌘1' },
  { to: '/library',     idx: '02', icon: FolderOpen,    label: '内容库',     en: 'library',    kbd: '⌘2' },
  { to: '/transcripts', idx: '03', icon: FileText,      label: '文稿库',     en: 'transcripts',kbd: '⌘3' },
  { to: '/discover',    idx: '04', icon: Compass,       label: '发现',       en: 'discover',   kbd: '⌘4' },
  { to: '/settings',    idx: '05', icon: Settings,      label: '设置',       en: 'settings',   kbd: '⌘5' },
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
          <span className="text-[11px] tracking-[0.16em] uppercase text-[var(--color-ash)]">
            <span className="font-display text-[14px] tracking-normal text-[var(--color-rust)] mr-1.5">{activeTasks.length}</span>
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
          className="absolute inset-y-0 left-0 bg-[var(--color-rust)] rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
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
      // ⌘1 .. ⌘5 = 导航到对应 navItems
      if ((e.metaKey || e.ctrlKey) && e.key >= '1' && e.key <= '5') {
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
  }, [navigate, setOpen, setTaskDrawerOpen]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[16vh]">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={() => setOpen(false)} />
      <div className="relative w-full max-w-lg bg-[var(--color-paper)] border border-[var(--color-hairline-strong)] shadow-[0_24px_64px_rgba(0,0,0,0.7)] overflow-hidden bloom-enter">
        {/* Header */}
        <div className="px-6 pt-5 pb-3 border-b border-[var(--color-hairline-faint)]">
          <div className="flex items-baseline justify-between mb-3">
            <span className="eyebrow">Command</span>
            <span className="mono-cap">esc</span>
          </div>
          <div className="flex items-center gap-3">
            <Search className="w-3.5 h-3.5 text-[var(--color-smoke)]" strokeWidth={1.5} />
            <input
              type="text"
              placeholder="键入命令、跳转或查询⋯"
              className="flex-1 bg-transparent font-display text-[22px] text-[var(--color-bone)] placeholder:text-[var(--color-smoke)] outline-none"
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
              className="w-full px-6 py-3 flex items-center gap-5 hover:bg-[rgba(255,255,255,0.03)] transition-colors group cursor-pointer"
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
      {/* ═══ LEFT RAIL ═══════════════════════════════════════════ */}
      <nav className="w-[76px] flex-shrink-0 border-r border-[var(--color-hairline-faint)] bg-[var(--color-paper)]/40 backdrop-blur-sm flex flex-col z-20">
        {/* Logomark */}
        <NavLink
          to="/home"
          onClick={() => setTaskDrawerOpen(false)}
          className="h-[76px] flex items-center justify-center border-b border-[var(--color-hairline-faint)] group"
          title="工作台"
        >
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-purple-600 flex items-center justify-center shadow-[0_0_15px_rgba(99,102,241,0.25)] group-hover:shadow-[0_0_22px_rgba(99,102,241,0.5)] transition-all duration-300">
            <span className="font-sans font-extrabold text-[19px] text-white tracking-wider">
              MS
            </span>
          </div>
        </NavLink>

        {/* Nav */}
        <div className="flex-1 flex flex-col py-4 px-2 space-y-1 stagger">
          {navItems.map((item) => {
            const isActive = location.pathname.startsWith(item.to)
              || (item.to === '/home' && location.pathname === '/');
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setTaskDrawerOpen(false)}
                title={`${item.label} (${item.kbd})`}
                className={`rail-item relative flex flex-col items-center justify-center py-3.5 px-2 transition-all duration-300 ${
                  isActive ? 'active text-[var(--color-rust)] bg-[rgba(99,102,241,0.08)]' : 'text-[var(--color-ash)] hover:text-[var(--color-bone)]'
                }`}
              >
                <item.icon className="w-[21px] h-[21px] transition-colors stroke-[1.8]" />
                <span className={`mt-1.5 text-[8.5px] font-medium tracking-[0.06em] uppercase scale-90 leading-none ${
                  isActive ? 'text-[var(--color-rust)] font-semibold' : 'text-[var(--color-smoke)]'
                }`}>
                  {item.en}
                </span>
              </NavLink>
            );
          })}
        </div>

        {/* Footer — minimal clock */}
        <div className="border-t border-[var(--color-hairline-faint)] py-3 flex justify-center">
          <span className="font-mono text-[11px] text-[var(--color-smoke)] tabular">{timeStr}</span>
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
