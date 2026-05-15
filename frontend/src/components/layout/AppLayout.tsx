import { useLocation } from 'react-router-dom';
import { useState, useMemo, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import Sidebar from './Sidebar';
import BottomNav from './BottomNav';
import { SearchOverlay } from '@/components/ui/SearchOverlay';
import { useStore } from '@/store/useStore';
import { getTaskDisplayState } from '@/lib/task-utils';

export default function AppLayout() {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const rawTasks = useStore((state) => state.tasks);

  const taskSummary = useMemo(() => {
    let active = 0;
    let failed = 0;
    for (const t of rawTasks) {
      const s = getTaskDisplayState(t);
      if (s === 'running' || s === 'paused') active++;
      else if (s === 'failed' || s === 'stale') failed++;
    }
    return { active, failed };
  }, [rawTasks]);

  // Keyboard shortcut: Cmd+K / Ctrl+K to open search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <div className="flex h-full w-full overflow-hidden bg-background">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} onOpenSearch={() => setSearchOpen(true)} />
      <main className="flex-1 flex flex-col h-full min-w-0 overflow-hidden">
        <div className="flex-1 min-h-0 overflow-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ type: 'spring', stiffness: 400, damping: 32 }}
              className="h-full"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </div>
        <BottomNav taskCount={taskSummary.active} onOpenSearch={() => setSearchOpen(true)} />
      </main>
      <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
