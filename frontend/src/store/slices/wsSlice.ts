import type { StateCreator } from 'zustand';
import type { Task } from '@/lib/api';
import { API_WS_URL } from '@/lib/api';
import type { StoreState } from '../useStore';

const WS_BASE_DELAY = 1000;
const WS_MAX_DELAY = 30_000;
const WS_MAX_RETRIES = 20;

export interface WsSlice {
  wsConnected: boolean;
  _wsRetryCount: number;
  _wsInstance: WebSocket | null;
  _wsRetryTimer: ReturnType<typeof setTimeout> | null;
  _wsClosing: boolean;
  _lastWsErrorLog: number;
  connectWebSocket: () => void;
  disconnectWebSocket: () => void;
}

export const createWsSlice: StateCreator<StoreState, [], [], WsSlice> = (set, get) => ({
  wsConnected: false,
  _wsRetryCount: 0,
  _wsInstance: null,
  _wsRetryTimer: null,
  _wsClosing: false,
  _lastWsErrorLog: 0,

  connectWebSocket: () => {
    // 已有有效连接或正在连接：直接返回
    const { _wsInstance, wsConnected } = get();
    if (wsConnected || (_wsInstance && (_wsInstance.readyState === WebSocket.OPEN || _wsInstance.readyState === WebSocket.CONNECTING))) {
      return;
    }

    // 重置 StrictMode 残留的 _wsClosing 状态，确保新连接不会被误判为主动断开
    if (get()._wsClosing) {
      set({ _wsClosing: false });
    }

    const ws = new WebSocket(API_WS_URL);
    set({ _wsInstance: ws });

    ws.onopen = () => {
      console.warn('Task WebSocket connected');
      set({ wsConnected: true, _wsRetryCount: 0 });
      get().fetchInitialTasks();
      get().fetchSettings();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // 收到 ping 立即回 pong，让服务端能基于 _last_activity 判定连接存活
        if (data.type === 'ping') {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: 'pong' }));
            } catch {
              // ignore: client send errors will surface via onclose
            }
          }
          return;
        }
        if (!data.task_id) return;
        const update: Partial<Task> & { task_id: string } = {
          task_id: data.task_id,
          progress: data.progress,
          status: data.status,
          task_type: data.task_type,
          update_time: data.update_time || new Date().toISOString(),
        };
        const msg = typeof data.msg === 'string' ? data.msg : '';
        if ('msg' in data || data.subtasks || data.result_summary || data.stage || data.pipeline_progress) {
          const existing = get().tasks.find((t) => t.task_id === data.task_id);
          let payload: Record<string, unknown> = {};
          if (existing?.payload) {
            try {
              const parsed = JSON.parse(existing.payload);
              if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                payload = parsed as Record<string, unknown>;
              }
            } catch {
              payload = {};
            }
          }
          if (msg) payload.msg = msg;
          if (data.subtasks) payload.subtasks = data.subtasks;
          if (data.result_summary) payload.result_summary = data.result_summary;
          if (data.stage || (data.pipeline_progress && typeof data.pipeline_progress === 'object' && !Array.isArray(data.pipeline_progress))) {
            const existingProgress = payload.pipeline_progress;
            const base =
              existingProgress && typeof existingProgress === 'object' && !Array.isArray(existingProgress)
                ? (existingProgress as Record<string, unknown>)
                : {};
            const incoming = (data.pipeline_progress && typeof data.pipeline_progress === 'object' && !Array.isArray(data.pipeline_progress))
              ? (data.pipeline_progress as Record<string, unknown>)
              : {};
            payload.pipeline_progress = { ...base, ...incoming, ...(data.stage ? { stage: data.stage } : {}) };
            if (data.stage) payload.stage = data.stage;
          }
          update.payload = JSON.stringify(payload);
        }
        if ((data.status === 'FAILED' || data.status === 'PARTIAL_FAILED') && msg) {
          update.error_msg = msg;
        }
        get().updateTask(update);
      } catch (e) {
        console.error('Failed to parse task WS message', e);
      }
    };

    ws.onclose = () => {
      // 如果已有新连接，忽略旧连接的 onclose（React StrictMode 会 mount→unmount→mount）
      if (get()._wsInstance !== ws) return;
      set({ wsConnected: false, _wsInstance: null });
      // 主动断开则不重连
      if (get()._wsClosing) {
        set({ _wsClosing: false });
        return;
      }
      const retryCount = get()._wsRetryCount;
      if (retryCount >= WS_MAX_RETRIES) {
        console.warn('Task WebSocket max retries reached, giving up');
        return;
      }
      // 清理已有的重连 timer，避免多个 timer 累积
      const existingTimer = get()._wsRetryTimer;
      if (existingTimer) {
        clearTimeout(existingTimer);
      }
      const delay = Math.min(WS_BASE_DELAY * Math.pow(2, retryCount), WS_MAX_DELAY);
      console.warn(`Task WebSocket disconnected, reconnecting in ${delay}ms (attempt ${retryCount + 1})`);
      set({ _wsRetryCount: retryCount + 1 });
      const timer = setTimeout(() => {
        get().connectWebSocket();
      }, delay);
      set({ _wsRetryTimer: timer });
    };

    ws.onerror = () => {
      const now = Date.now();
      if (now - get()._lastWsErrorLog < 1000) return;
      set({ _lastWsErrorLog: now });
      console.error('Task WebSocket error');
      ws.close();
    };
  },

  disconnectWebSocket: () => {
    const { _wsInstance, _wsRetryTimer } = get();
    if (_wsRetryTimer) {
      clearTimeout(_wsRetryTimer);
    }
    if (_wsInstance) {
      set({ _wsClosing: true });
      _wsInstance.close();
    }
    set({ _wsInstance: null, wsConnected: false, _wsRetryTimer: null, _wsRetryCount: 0, _wsClosing: false, _lastWsErrorLog: 0 });
  },
});
