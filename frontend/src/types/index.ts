export interface Creator {
  uid: string;
  nickname: string;
  sec_user_id: string;
  platform?: string;
  sync_status: string;
  avatar?: string;
  bio?: string;
  homepage_url?: string;
  last_fetch_time?: string | null;
  asset_count?: number;
  downloaded_videos_count?: number;
  transcript_completed_count?: number;
  transcript_pending_count?: number;
  transcript_failed_count?: number;
  unread_completed_count?: number;
  disk_asset_count?: number;
  disk_transcript_completed_count?: number;
  disk_transcript_pending_count?: number;
  auto_sync?: boolean | 0 | 1;
}

export interface Asset {
  asset_id: string;
  creator_uid: string;
  creator_name?: string | null;
  title: string;
  video_status: string;
  transcript_status: string;
  transcript_path: string;
  transcript_preview?: string;
  folder_path?: string;
  is_read?: boolean;
  is_starred?: boolean;
  create_time?: string;
  update_time?: string;
  transcript_error_type?: string | null;
  transcript_last_error?: string | null;
  transcript_retry_count?: number | null;
  transcript_failed_at?: string | null;
  source_platform?: string | null;
  last_task_id?: string | null;
}

export interface Task {
  task_id: string;
  task_type: string;
  status: string;
  progress: number;
  payload: string;
  error_msg?: string;
  auto_retry?: boolean | number;
  update_time?: string;
  priority?: number;
}

export type PipelineProgressStage =
  | 'fetching'
  | 'auditing'
  | 'downloading'
  | 'uploading'
  | 'transcribing'
  | 'exporting'
  | 'completed'
  | 'failed'
  | string;

export type TaskStage =
  | 'created'
  | 'fetching'
  | 'auditing'
  | 'downloading'
  | 'transcribing'
  | 'exporting'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface DownloadStageProgress {
  downloaded: number;
  skipped: number;
  failed: number;
  total: number;
  current_video: string;
  current_video_progress: number;
  current_index: number;
}

export interface TranscribeStageProgress {
  done: number;
  skipped: number;
  failed: number;
  total: number;
  current_video: string;
  current_account: string;
}

export interface TaskProgress {
  stage: TaskStage;
  stage_label: string;
  stage_icon: string;
  overall_percent: number;
  download_progress: DownloadStageProgress | null;
  transcribe_progress: TranscribeStageProgress | null;
  error_count: number;
  errors: Array<{
    code: string;
    message: string;
    suggestion: string;
    timestamp: string;
  }>;
  start_time: string | null;
  estimated_time_remaining: string | null;
  message: string;
}

export interface PipelineProgressCounter {
  done: number;
  total: number;
  account_id?: string;
  current_title?: string;
  current_aweme_id?: string;
  skipped?: number;
  current_index?: number;
}

export interface PipelineProgressExport {
  done: 0 | 1;
  total: 1;
  file?: string | null;
  status?: string | number | null;
}

export interface PipelineProgress {
  stage: PipelineProgressStage;
  list?: PipelineProgressCounter;
  audit?: { missing: number };
  download?: PipelineProgressCounter;
  transcribe?: PipelineProgressCounter;
  export?: PipelineProgressExport;
}

export interface ScheduleTask {
  task_id: string;
  task_type: string;
  cron_expr: string;
  enabled: boolean;
  update_time: string;
}

export interface ScannedFile {
  path: string;
  name: string;
  size_mb: number;
}

export interface DouyinVideoMeta {
  aweme_id: string;
  desc: string;
  create_time: number;
  video_url: string;
  cover_url: string;
}

export interface DouyinCreatorMeta {
  uid: string;
  nickname: string;
  avatar: string;
}

export interface DouyinMetadataResponse {
  creator: DouyinCreatorMeta;
  videos: DouyinVideoMeta[];
}

export interface QwenStatusAccount {
  account_id: string;
  account_label?: string;
  remaining_hours: number;
  status?: string;
}

export interface QwenStatusResponse {
  status: string;
  accounts: QwenStatusAccount[];
  message?: string;
}

export interface AddQwenAccountResponse {
  account_id: string;
  remaining_hours: number;
}