import { Loader2, Download, FileAudio, Plus, ExternalLink } from 'lucide-react';
import { LinkInfo, PLATFORM_LABEL, TYPE_LABEL } from './discoverUtils';

interface DirectLinkCardProps {
  linkInfo: LinkInfo;
  url: string;
  submitting: boolean;
  onDirectDownload: () => void;
  onDirectTranscribe: () => void;
  onCollect?: () => void;
  collecting?: boolean;
}

export function DirectLinkCard({
  linkInfo,
  url,
  submitting,
  onDirectDownload,
  onDirectTranscribe,
  onCollect,
  collecting = false,
}: DirectLinkCardProps) {
  return (
    <div className="max-w-xl">
      <div className="bg-black/[0.04] backdrop-blur border border-black/10 rounded-2xl p-6">
        <div className="flex items-center gap-3 mb-4">
          <span className="mono-cap text-[var(--color-rust)]">
            {PLATFORM_LABEL[linkInfo.platform]}
          </span>
          <span className="text-[var(--color-ash)] text-[12px]">
            {TYPE_LABEL[linkInfo.type]}
          </span>
        </div>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-[13px] text-[var(--color-ash)] mb-6 break-all flex items-start gap-2 hover:text-[var(--color-rust)] transition-colors"
        >
          <ExternalLink className="w-3.5 h-3.5 mt-0.5 shrink-0" strokeWidth={1.5} />
          {url}
        </a>
        {(linkInfo.type === 'up_space' || (linkInfo.platform === 'youtube' && linkInfo.type === 'profile')) && (
          <div className="text-[12px] text-[var(--color-ash)] mb-4">
            将同步该创作者的最新视频
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onDirectDownload}
            disabled={submitting}
            className="btn-sharp disabled:opacity-40 flex items-center gap-2"
          >
            {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            仅下载
          </button>
          <button
            onClick={onDirectTranscribe}
            disabled={submitting}
            className="btn-sharp btn-primary disabled:opacity-40 flex items-center gap-2"
          >
            {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileAudio className="w-3.5 h-3.5" />}
            下载 + 转写
          </button>
          {(linkInfo.type === 'up_space' || linkInfo.type === 'profile') && onCollect && (
            <button
              onClick={onCollect}
              disabled={collecting}
              className="btn-sharp border-[var(--color-rust)] text-[var(--color-rust)] hover:bg-[rgba(0,113,227,0.05)] disabled:opacity-40 flex items-center gap-2"
            >
              {collecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              收录为创作者
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
