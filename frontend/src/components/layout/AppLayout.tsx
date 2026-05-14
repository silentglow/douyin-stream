import { useLocation } from 'react-router-dom';
import { useState, useMemo } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import BottomNav from './BottomNav';
import { cn } from '@/lib/utils';
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
    <div className="flex h-full w-full overflow-hidden" style={{ background: '#F2F2F7' }}>
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="flex-1 flex flex-col h-full min-w-0 overflow-hidden">
        <div className="flex-1 min-h-0 overflow-auto">
          <div
            key={`${location.pathname}${location.search}`}
            className={cn('h-full', 'apple-fade-in')}
          >
            <Outlet />
          </div>
        </div>
        <BottomNav taskCount={taskSummary.active} />
      </main>
    </div>
  );
}
