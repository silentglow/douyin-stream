import { ExternalLink, Download, HardDriveDownload, Loader2, RefreshCcw, Trash2, FileText, AlertTriangle, Clock, Folder, FileCheck, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Toggle } from '@/components/ui/toggle';
import { formatRelativeTime, getTaskDisplayState, getTaskError, getTaskMessage } from '@/lib/task-utils';
import type { Creator, Task } from '@/lib/api';

interface CreatorCardProps {
  creator: Creator;
  tasks: Task[];
  downloadingCreators: Record<string, 'incremental' | 'full' | null>;
  isDeleting: boolean;
  onDownload: (uid: string, nickname: string, mode: 'incremental' | 'full') => void;
  onTranscribe: (uid: string, nickname: string, deleteAfter?: boolean) => void;
  transcribingUids: Set<string>;
  onRetryFailed: (uid: string, nickname: string) => void;
  retryingFailedUids: Set<string>;
  onDelete: (uid: string) => void;
  settings?: {
    status_summary?: {
      douyin_ready?: boolean;
      bilibili_accounts_count?: number;
      douyin_primary_configured?: boolean;
      douyin_cookie_source?: 'config' | 'pool' | 'none' | string;
    };
  } | null;
  deleteAfterTranscribe: boolean;
  setDeleteAfterTranscribe: (v: boolean) => void;
}

function getCreatorPlatform(creator: Creator): 'douyin' | 'bilibili' | 'local' {
  if (creator.platform === 'bilibili' || creator.uid.startsWith('bilibili:')) return 'bilibili';
  if (creator.platform === 'local' || creator.uid.startsWith('local:')) return 'local';
  return 'douyin';
}

function findRelatedTask(creator: Creator, tasks: Task[]) {
  const keywords = [creator.uid, creator.nickname].filter(Boolean) as string[];
  return tasks.find((task) => {
    if (!task.task_type.startsWith('creator_sync_')) return false;
    const haystacks = [task.payload || '', task.error_msg || ''];
    return keywords.some((keyword) => haystacks.some((value) => value.includes(keyword)));
  });
}

export function CreatorCard({
  creator,
  tasks,
  downloadingCreators,
  isDeleting,
  onDownload,
  onTranscribe,
  transcribingUids,
  onRetryFailed,
  retryingFailedUids,
  onDelete,
  settings,
  deleteAfterTranscribe,
  setDeleteAfterTranscribe,
}: CreatorCardProps) {
  const platform = getCreatorPlatform(creator);
  const isBusy = !!downloadingCreators[creator.uid];
  const relatedTask = findRelatedTask(creator, tasks);
  const taskState = relatedTask ? getTaskDisplayState(relatedTask) : null;
  const taskMessage = relatedTask ? getTaskMessage(relatedTask) : '';
  const taskError = relatedTask ? getTaskError(relatedTask) : '';

  const douyinReady = settings?.status_summary?.douyin_ready ?? false;
  const bilibiliReady = (settings?.status_summary?.bilibili_accounts_count ?? 0) > 0;
  const douyinPrimaryConfigured = settings?.status_summary?.douyin_primary_configured ?? false;
  const douyinCookieSource = settings?.status_summary?.douyin_cookie_source ?? 'none';

  const creatorReady = platform === 'bilibili' ? bilibiliReady : platform === 'local' ? false : douyinReady;

  const statusBadge = platform === 'local'
    ? { label: '本地素材', tone: 'default' as const }
    : !creatorReady
      ? {
          label: platform === 'bilibili' ? '缺少B站账号' : '缺少抖音账号',
          tone: 'destructive' as const,
        }
      : isBusy || taskState === 'running'
        ? { label: '同步中', tone: 'secondary' as const }
        : taskState === 'failed' || taskState === 'stale'
          ? creator.last_fetch_time
            ? { label: '同步异常', tone: 'destructive' as const }
            : { label: '首次同步失败', tone: 'destructive' as const }
          : creator.last_fetch_time
            ? { label: '可同步', tone: 'secondary' as const }
            : { label: '待首次同步', tone: 'default' as const };

  return (
    <Card 
      size="default" 
      className={cn(
        "group",
        isDeleting && "opacity-0 scale-95 transition-all duration-300"
      )}
    >
      <CardContent className="space-y-4">
        {/* Header */}
        <div className="flex items-start gap-4">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-primary/15 to-primary/5 text-lg font-semibold text-foreground">
            {(creator.nickname || creator.uid).charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-title-3 font-semibold text-foreground line-clamp-1">
                {creator.nickname || creator.uid}
              </h3>
              {creator.homepage_url && (
                <a
                  href={creator.homepage_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="size-7 rounded-[8px] flex items-center justify-center text-muted-foreground transition-all duration-200 hover:bg-primary/10 hover:text-primary"
                  title="打开主页"
                >
                  <ExternalLink className="size-4" />
                </a>
              )}
              <Badge tone={statusBadge.tone}>{statusBadge.label}</Badge>
            </div>
            
            {/* Stats */}
            <div className="grid grid-cols-3 gap-2 mt-3">
              <div className="flex items-center gap-1.5">
                <Folder className="size-3.5 text-muted-foreground" />
                <span className="text-caption text-muted-foreground">
                  <strong className="text-foreground font-semibold">{creator.disk_asset_count ?? 0}</strong>
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <FileCheck className="size-3.5 text-muted-foreground" />
                <span className="text-caption text-muted-foreground">
                  <strong className="text-foreground font-semibold">{creator.disk_transcript_completed_count ?? 0}</strong>
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <Clock className="size-3.5 text-muted-foreground" />
                <span className="text-caption text-muted-foreground">
                  <strong className="text-foreground font-semibold">{creator.disk_transcript_pending_count ?? 0}</strong>
                </span>
              </div>
            </div>
            
            {(creator.transcript_failed_count ?? 0) > 0 && (
              <div className="mt-1.5 flex items-center gap-1.5 text-destructive">
                <AlertCircle className="size-3.5" />
                <span className="text-caption">
                  <strong className="font-semibold">{creator.transcript_failed_count}</strong> 个转写失败
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Last sync info */}
        <div className="apple-list-item rounded-[10px] px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-caption text-muted-foreground">上次同步</span>
            <span className="text-caption font-medium text-foreground tabular-nums">
              {formatRelativeTime(creator.last_fetch_time)}
            </span>
          </div>
        </div>

        {/* Task message */}
        {taskMessage && taskMessage !== '暂无详细信息' && (
          <div className="text-caption text-muted-foreground">{taskMessage}</div>
        )}
        
        {/* Task error */}
        {taskError && (
          <div className="rounded-[10px] border border-destructive/20 bg-destructive/10 p-3 text-caption text-destructive">
            {taskError}
          </div>
        )}

        {/* Action buttons */}
        <div className="grid grid-cols-3 gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onDownload(creator.uid, creator.nickname, 'incremental')}
            disabled={!creatorReady || isBusy || platform === 'local'}
          >
            {downloadingCreators[creator.uid] === 'incremental' ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
            <span className="text-[13px]">增量</span>
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onDownload(creator.uid, creator.nickname, 'full')}
            disabled={!creatorReady || isBusy || platform === 'local'}
          >
            {downloadingCreators[creator.uid] === 'full' ? <Loader2 className="size-3.5 animate-spin" /> : <HardDriveDownload className="size-3.5" />}
            <span className="text-[13px]">全量</span>
          </Button>
          {(creator.disk_transcript_pending_count ?? 0) > 0 && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => onTranscribe(creator.uid, creator.nickname, deleteAfterTranscribe)}
              disabled={transcribingUids.has(creator.uid)}
            >
              {transcribingUids.has(creator.uid) ? <Loader2 className="size-3.5 animate-spin" /> : <FileText className="size-3.5" />}
              <span className="text-[13px]">转写</span>
            </Button>
          )}
        </div>

        {(creator.disk_transcript_pending_count ?? 0) > 0 && (
          <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
            <span>转写后删除源视频</span>
            <Toggle checked={deleteAfterTranscribe} onChange={setDeleteAfterTranscribe} />
          </div>
        )}

        {/* Retry failed button */}
        {(creator.transcript_failed_count ?? 0) > 0 && (
          <Button
            variant="ghostDestructive"
            size="sm"
            onClick={() => onRetryFailed(creator.uid, creator.nickname)}
            disabled={retryingFailedUids.has(creator.uid)}
            className="w-full"
          >
            {retryingFailedUids.has(creator.uid)
              ? <Loader2 className="size-3.5 animate-spin" />
              : <AlertTriangle className="size-3.5" />}
            <span className="text-[13px]">重试失败 ({creator.transcript_failed_count})</span>
          </Button>
        )}

        {/* Footer */}
        <div className="apple-list-item rounded-[10px] px-4 py-3 mt-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <RefreshCcw className="size-3.5 text-muted-foreground" />
              <span className="text-caption text-muted-foreground">
                {platform === 'local'
                  ? '本地导入素材不支持远程同步'
                  : !creatorReady
                    ? platform === 'bilibili'
                      ? '请先配置B站账号'
                      : '请先配置抖音账号'
                    : platform === 'bilibili'
                      ? `使用B站账号池 (${settings?.status_summary?.bilibili_accounts_count ?? 0})`
                      : douyinPrimaryConfigured
                        ? '使用主 Cookie'
                        : douyinCookieSource === 'pool'
                          ? '使用账号池 Cookie'
                          : '使用可用配置'}
              </span>
            </div>
            <Button
              variant="ghostDestructive"
              size="iconSm"
              onClick={() => onDelete(creator.uid)}
              className="h-7"
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
