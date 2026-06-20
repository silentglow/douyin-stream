import { Loader2, Download, FileAudio, ExternalLink } from 'lucide-react';
import { LinkInfo, PLATFORM_LABEL, TYPE_LABEL } from './discoverUtils';

interface DirectLinkCardProps {
  linkInfo: LinkInfo;
  url: string;
  submitting: boolean;
  onDirectDownload: () => void;
  onDirectTranscribe: () => void;
}

export function DirectLinkCard({
  linkInfo,
  url,
  submitting,
  onDirectDownload,
  onDirectTranscribe,
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
        {linkInfo.type === 'up_space' && (
          <div className="text-[12px] text-[var(--color-ash)] mb-4">
            将下载该 UP 主的最新视频（最多 20 个）
          </div>
        )}
        <div className="flex gap-2">
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
        </div>
      </div>
    </div>
  );
}
