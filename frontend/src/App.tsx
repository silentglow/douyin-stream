import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from 'next-themes';
import AppLayout from './components/layout/AppLayout';
import { Toaster } from '@/components/ui/sonner';
import { useEffect, Component, type ReactNode, lazy } from 'react';
import { useStore } from './store/useStore';

// Lazy load pages for code splitting
const Discovery = lazy(() => import('./pages/Discovery'));
const Creators = lazy(() => import('./pages/Creators'));
const Settings = lazy(() => import('./pages/Settings'));
const Dashboard = lazy(() => import('./pages/Dashboard'));

class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen items-center justify-center bg-background p-8">
          <div className="max-w-md space-y-4 text-center">
            <div className="text-lg font-semibold text-foreground">页面渲染出错</div>
            <div className="text-sm text-muted-foreground">{this.state.error?.message}</div>
            <button
              onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              重新加载
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  const connectWebSocket = useStore((state) => state.connectWebSocket);
  const disconnectWebSocket = useStore((state) => state.disconnectWebSocket);
  const lastCompletedTaskTime = useStore((state) => state.lastCompletedTaskTime);
  const fetchCreators = useStore((state) => state.fetchCreators);

  useEffect(() => {
    connectWebSocket();
    return () => { disconnectWebSocket(); };
  }, [connectWebSocket, disconnectWebSocket]);

  // 全局监听任务完成，任意页面都能触发创作者数据刷新
  useEffect(() => {
    if (lastCompletedTaskTime > 0) {
      fetchCreators(true);
    }
  }, [lastCompletedTaskTime, fetchCreators]);

  return (
    <ThemeProvider attribute="class" defaultTheme="light">
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/creators" replace />} />
            <Route element={<AppLayout />}>
              <Route path="/discover" element={<Discovery />} />
              <Route path="/creators" element={<Creators />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/settings" element={<Settings />} />
            </Route>
          </Routes>
          <Toaster />
        </BrowserRouter>
      </ErrorBoundary>
    </ThemeProvider>
  );
}

export default App;
