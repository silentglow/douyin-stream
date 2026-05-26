import type { Task } from '@/lib/api';
import type { TaskProgress } from '@/types';
import { truncateText } from './formatters';

export function getProgressPercent(task: Task, progress?: TaskProgress | null): number {
  if (progress?.overall_percent !== undefined && progress.overall_percent !== null) {
    return Math.round(progress.overall_percent);
  }

  if (progress?.download_progress) {
    const { downloaded, skipped, total } = progress.download_progress;
    if (total > 0) {
      return Math.round(((downloaded + skipped) / total) * 100);
    }
  }

  return Math.round((task.progress || 0) * 100);
}

export function getProgressDetails(_task: Task, progress?: TaskProgress | null): string {
  if (!progress) return '';

  const parts: string[] = [];

  if (progress.download_progress) {
    const { downloaded, skipped, failed, total } = progress.download_progress;
    const dlParts: string[] = [];
    if (downloaded > 0) dlParts.push(`${downloaded}`);
    if (skipped > 0) dlParts.push(`跳过${skipped}`);
    if (failed > 0) dlParts.push(`失败${failed}`);
    if (dlParts.length > 0) {
      parts.push(`下载 ${dlParts.join('/')}/${total}`);
    }
  }

  if (progress.transcribe_progress) {
    const { done, skipped, failed, total } = progress.transcribe_progress;
    const tpParts: string[] = [];
    if (done > 0) tpParts.push(`${done}`);
    if (skipped > 0) tpParts.push(`跳过${skipped}`);
    if (failed > 0) tpParts.push(`失败${failed}`);
    if (tpParts.length > 0) {
      parts.push(`转写 ${tpParts.join('/')}/${total}`);
    }
  }

  return parts.join('，');
}

export function formatStageMessage(task: Task, progress?: TaskProgress | null): string {
  if (!progress) {
    return parseTaskMessage(task.payload) || '';
  }

  if (progress.message) {
    return progress.message;
  }

  const { stage, download_progress, transcribe_progress, error_count } = progress;

  if (stage === 'fetching') {
    return '正在获取视频列表...';
  }

  if (stage === 'auditing') {
    const total = download_progress?.total || 0;
    const downloaded = download_progress?.downloaded || 0;
    const skipped = download_progress?.skipped || 0;
    const pending = total - downloaded - skipped;
    return pending > 0
      ? `对账中：发现 ${downloaded + skipped} 个本地已有，${pending} 个待下载`
      : `对账完成：全部 ${total} 个视频已存在`;
  }

  if (stage === 'downloading' && download_progress) {
    const { downloaded, total, current_video } = download_progress;
    const videoLabel = current_video ? `：${truncateText(current_video, 40)}` : '';
    return `正在下载 (${downloaded + 1}/${total})${videoLabel}`;
  }

  if (stage === 'transcribing' && transcribe_progress) {
    const { done, total, current_video, current_account } = transcribe_progress;
    const accountLabel = current_account ? ` [${current_account}]` : '';
    const videoLabel = current_video ? `：${truncateText(current_video, 40)}` : '';
    return `正在转写 (${done + 1}/${total})${accountLabel}${videoLabel}`;
  }

  if (stage === 'exporting') {
    return '正在导出字幕文件...';
  }

  if (stage === 'completed') {
    const dl = download_progress;
    const tp = transcribe_progress;
    const parts: string[] = [];
    if (dl) {
      if (dl.downloaded > 0) parts.push(`下载 ${dl.downloaded}/${dl.total}`);
      if (dl.failed > 0) parts.push(`失败 ${dl.failed}`);
    }
    if (tp) {
      if (tp.done > 0) parts.push(`转写 ${tp.done}/${tp.total}`);
      if (tp.failed > 0) parts.push(`转写失败 ${tp.failed}`);
    }
    if (parts.length > 0) {
      return `已完成：${parts.join('，')}`;
    }
    return '已完成';
  }

  if (stage === 'failed') {
    if (error_count && error_count > 0) {
      return `失败：${error_count} 个错误`;
    }
    return '失败';
  }

  if (stage === 'cancelled') {
    return '已取消';
  }

  return parseTaskMessage(task.payload) || '';
}

import { parseTaskMessage } from './display-state';
