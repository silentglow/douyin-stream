import { useLocation } from 'react-router-dom';
import { useState, useMemo } from 'react';
import { Outlet } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import Sidebar from './Sidebar';
import BottomNav from './BottomNav';
import { useStore } from '@/store/useStore';
import { getTaskDisplayState } from '@/lib/task-utils';

export default function AppLayout() {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
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

  return (
    <div className="flex h-full w-full overflow-hidden bg-background">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="flex-1 flex flex-col h-full min-w-0 overflow-hidden">
        <div className="flex-1 min-h-0 overflow-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25, ease: [0.32, 0.72, 0, 1] }}
              className="h-full"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </div>
        <BottomNav taskCount={taskSummary.active} />
      </main>
    </div>
  );
}
