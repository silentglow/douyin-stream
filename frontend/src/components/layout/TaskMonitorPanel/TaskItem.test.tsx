import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { TaskItem } from './TaskItem'
import { rerunTask, retryFailedSubtasks } from '@/lib/api'
import { toast } from 'sonner'

vi.mock('@/lib/api', () => ({
  cancelTask: vi.fn(),
  rerunTask: vi.fn(),
  retryFailedSubtasks: vi.fn(),
  setAutoRetry: vi.fn(),
  deleteTask: vi.fn(),
  recoverAwemeAndTranscribe: vi.fn(),
  retryCreatorTranscribeCleanup: vi.fn(async () => ({
    task_id: 'running-export-meta-1',
    deleted_count: 1,
    failed_count: 0,
    failed_paths: [],
    total_deleted_count: 2,
  })),
}))

vi.mock('@/store/useStore', () => {
  const fetchInitialTasks = vi.fn(async () => void 0)
  const useStore = (() => ({})) as unknown as { getState: () => { fetchInitialTasks: () => Promise<void> } }
  useStore.getState = () => ({ fetchInitialTasks })
  return { useStore }
})

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('TaskItem', () => {
  it('shows clarified controls for FAILED', () => {
    render(
      <TaskItem
        task={{
          task_id: 'failed-1',
          task_type: 'pipeline',
          status: 'FAILED',
          progress: 0,
          payload: JSON.stringify({ msg: 'x' }),
          auto_retry: 0,
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={false}
        onToggleExpand={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '自动重试: 关' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '恢复' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '停止' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument()
  })

  it('shows clarified controls for PAUSED', () => {
    render(
      <TaskItem
        task={{
          task_id: 'paused-1',
          task_type: 'pipeline',
          status: 'PAUSED',
          progress: 0.5,
          payload: JSON.stringify({ msg: 'x' }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={false}
        onToggleExpand={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: '恢复' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /自动重试:/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument()
  })

  it('shows clarified controls for RUNNING', () => {
    render(
      <TaskItem
        task={{
          task_id: 'running-1',
          task_type: 'pipeline',
          status: 'RUNNING',
          progress: 0.5,
          payload: JSON.stringify({ msg: 'x' }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={false}
        onToggleExpand={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: '停止' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '恢复' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重试' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /自动重试:/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument()
  })

  it('falls back to legacy progress bar when pipeline_progress missing', () => {
    render(
      <TaskItem
        task={{
          task_id: 'running-legacy-1',
          task_type: 'pipeline',
          status: 'RUNNING',
          progress: 0.25,
          payload: JSON.stringify({ msg: 'x' }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={false}
        onToggleExpand={vi.fn()}
      />,
    )

    expect(screen.getByText('x')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
    expect(screen.queryByText(/列表/)).not.toBeInTheDocument()
  })

  it('shows remaining workload badge computed from pipeline_progress.download', () => {
    render(
      <TaskItem
        task={{
          task_id: 'running-export-1',
          task_type: 'pipeline',
          status: 'RUNNING',
          progress: 0.85,
          payload: JSON.stringify({
            msg: 'x',
            pipeline_progress: {
              stage: 'download',
              list: { done: 58, total: 58 },
              audit: { missing: 2 },
              download: { done: 3, total: 5 },
              transcribe: { done: 1, total: 5 },
              export: { done: 0, total: 1, file: 'out.md', status: 'polling' },
            },
          }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={false}
        onToggleExpand={vi.fn()}
      />
    )

    expect(screen.getByText('剩余 2 条')).toBeInTheDocument()
    expect(screen.getByText(/下载 3\/5/)).toBeInTheDocument()
    expect(screen.getByText(/缺失 2/)).toBeInTheDocument()
  })

  it('shows transcribe progress and current title for local_transcribe tasks when pipeline_progress provides it', () => {
    render(
      <TaskItem
        task={{
          task_id: 'running-local-transcribe-1',
          task_type: 'local_transcribe',
          status: 'RUNNING',
          progress: 0.1,
          payload: JSON.stringify({
            msg: 'x',
            pipeline_progress: {
              stage: 'transcribe',
              transcribe: { done: 2, total: 8, current_title: '测试文件A' },
            },
          }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={false}
        onToggleExpand={vi.fn()}
      />
    )

    expect(screen.getByText(/转写 2\/8/)).toBeInTheDocument()
    expect(screen.getByText(/当前：测试文件A/)).toBeInTheDocument()
    expect(screen.getByText(/剩余 6 条/)).toBeInTheDocument()
  })

  it('renders -- instead of 0/0 when totals missing in pipeline_progress', () => {
    render(
      <TaskItem
        task={{
          task_id: 'running-missing-total-1',
          task_type: 'pipeline',
          status: 'RUNNING',
          progress: 0.3,
          payload: JSON.stringify({
            msg: 'x',
            pipeline_progress: {
              stage: 'download',
              download: { done: 1, total: 0 },
            },
          }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={true}
        onToggleExpand={vi.fn()}
      />,
    )

    expect(screen.queryByText('0/0')).not.toBeInTheDocument()
    expect(screen.getByText(/1\/--/)).toBeInTheDocument()
  })

  it('shows friendly error label and suggestion for failed subtasks', () => {
    render(
      <TaskItem
        task={{
          task_id: 'completed-subtasks-1',
          task_type: 'local_transcribe',
          status: 'COMPLETED',
          progress: 1,
          payload: JSON.stringify({
            msg: 'ok',
            subtasks: [
              { title: 'a', status: 'failed', error: 'timeout: request timed out (attempts=2)', error_type: 'timeout' },
            ],
          }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={true}
        onToggleExpand={vi.fn()}
      />
    )

    expect(screen.getByText('网络超时')).toBeInTheDocument()
    expect(screen.getByText('建议：重试或检查网络')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试任务' })).toBeInTheDocument()
  })

  it('triggers retry-failed when clicking failed-only action', async () => {
    const retryFailed = vi.mocked(retryFailedSubtasks)
    retryFailed.mockResolvedValueOnce({ task_id: 'new-task-1', status: 'started', file_count: 1 })

    render(
      <TaskItem
        task={{
          task_id: 'failed-subtasks-paths',
          task_type: 'local_transcribe',
          status: 'FAILED',
          progress: 1,
          payload: JSON.stringify({
            msg: 'failed',
            subtasks: [{ title: 'a', status: 'failed', error: 'timeout', video_path: '/tmp/a.mp4' }],
          }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={false}
        onToggleExpand={vi.fn()}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '只重试失败 (1)' }))
    await waitFor(() => expect(retryFailed).toHaveBeenCalledWith('failed-subtasks-paths'))
    expect(vi.mocked(toast.success)).toHaveBeenCalled()
  })

  it('triggers retry-failed when clicking retry action on COMPLETED task with failed subtask', async () => {
    const retryFailed = vi.mocked(retryFailedSubtasks)
    retryFailed.mockResolvedValueOnce({ task_id: 'new-task-2', status: 'started', file_count: 1 })

    render(
      <TaskItem
        task={{
          task_id: 'completed-subtasks-2',
          task_type: 'local_transcribe',
          status: 'COMPLETED',
          progress: 1,
          payload: JSON.stringify({
            msg: 'ok',
            subtasks: [{ title: 'a', status: 'failed', error: 'timeout: request timed out', error_type: 'timeout', video_path: '/tmp/a.mp4' }],
          }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={true}
        onToggleExpand={vi.fn()}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '重试任务' }))
    await waitFor(() => expect(retryFailed).toHaveBeenCalledWith('completed-subtasks-2'))
    expect(vi.mocked(toast.success)).toHaveBeenCalled()
  })

  it('triggers rerun when clicking retry action on FAILED task with failed subtask', async () => {
    const rerun = vi.mocked(rerunTask)
    rerun.mockResolvedValueOnce({ task_id: 'new-task-1', status: 'started' } as never)

    render(
      <TaskItem
        task={{
          task_id: 'failed-task-rerun',
          task_type: 'local_transcribe',
          status: 'FAILED',
          progress: 1,
          payload: JSON.stringify({
            msg: 'failed',
            subtasks: [{ title: 'a', status: 'failed', error: 'timeout: request timed out', error_type: 'timeout', video_path: '/tmp/a.mp4' }],
          }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={true}
        onToggleExpand={vi.fn()}
      />
    )

    const buttons = screen.getAllByRole('button', { name: '重试任务' })
    // 第一个是顶层的"重试任务"按钮（来自 TaskActions 区域），子任务里的"重试任务"
    // 应当是最后一个；不同视图下出现顺序可能不同，这里挑最末尾的那个触发
    fireEvent.click(buttons[buttons.length - 1])
    await waitFor(() => expect(rerun).toHaveBeenCalledWith('failed-task-rerun'))
    expect(vi.mocked(toast.success)).toHaveBeenCalled()
  })

  it('navigates to settings when clicking open-settings action', () => {
    window.history.pushState({}, '', '/creators')
    render(
      <TaskItem
        task={{
          task_id: 'completed-subtasks-3',
          task_type: 'local_transcribe',
          status: 'COMPLETED',
          progress: 1,
          payload: JSON.stringify({
            msg: 'ok',
            subtasks: [{ title: 'a', status: 'failed', error: 'auth: 401', error_type: 'auth' }],
          }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={true}
        onToggleExpand={vi.fn()}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '去设置' }))
    expect(window.location.pathname).toBe('/settings')
  })

  it('toggles drawer when clicking collapsed row', () => {
    const onToggleExpand = vi.fn()
    render(
      <TaskItem
        task={{
          task_id: 'running-toggle-1',
          task_type: 'pipeline',
          status: 'RUNNING',
          progress: 0.85,
          payload: JSON.stringify({
            msg: 'x',
            pipeline_progress: {
              stage: 'download',
              download: { done: 1, total: 3 },
            },
          }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={false}
        onToggleExpand={onToggleExpand}
      />
    )

    screen.getByRole('button', { name: /剩余 2 条/ }).click()
    expect(onToggleExpand).toHaveBeenCalledWith('running-toggle-1')
  })

  it('shows cleanup summary and retry button in drawer', async () => {
    render(
      <TaskItem
        task={{
          task_id: 'running-export-meta-1',
          task_type: 'pipeline',
          status: 'RUNNING',
          progress: 0.85,
          payload: JSON.stringify({
            msg: 'x',
            pipeline_progress: {
              stage: 'download',
              list: { done: 58, total: 58 },
              audit: { missing: 2 },
              download: { done: 3, total: 5 },
              transcribe: { done: 1, total: 5 },
              export: { done: 0, total: 1, file: 'out.md', status: 'polling' },
            },
            cleanup_deleted_count: 1,
            cleanup_failed_count: 2,
            cleanup_failed_paths: [
              { path: '/tmp/a', reason: 'corrupt_file' },
              { path: '/tmp/b', reason: 'http_403' },
            ],
          }),
          error_msg: '',
          update_time: new Date().toISOString(),
        }}
        onRetry={vi.fn()}
        isExpanded={true}
        onToggleExpand={vi.fn()}
      />,
    )

    // 导出信息已在摘要行显示（subtitle），抽屉不再单独显示导出卡片

    expect(screen.getByText('清理汇总')).toBeInTheDocument()
    expect(screen.getByText('成功 1 · 失败 2 · 共 3')).toBeInTheDocument()
    expect(screen.getByText('文件异常 × 1')).toBeInTheDocument()
    expect(screen.getByText('403 无权限 × 1')).toBeInTheDocument()

    const retryButton = screen.getByRole('button', { name: '重试清理' })
    expect(retryButton).toBeEnabled()

    await act(async () => {
      fireEvent.click(retryButton)
    })

    const { retryCreatorTranscribeCleanup } = await import('@/lib/api')
    const { useStore } = await import('@/store/useStore')
    const { toast } = await import('sonner')

    await waitFor(() => {
      expect(vi.mocked(retryCreatorTranscribeCleanup)).toHaveBeenCalledWith('running-export-meta-1')
    })
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(useStore.getState().fetchInitialTasks).toHaveBeenCalled()
    })
  })

})
