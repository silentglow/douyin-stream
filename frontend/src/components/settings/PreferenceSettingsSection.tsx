import { Zap, Trash2, FileText, Globe } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { SettingsGroup, SettingsItem } from '@/components/settings/SettingsLayout';

interface PreferenceSettingsSectionProps {
  autoTranscribe: boolean;
  handleToggleAutoTranscribe: (v: boolean) => void;
  autoDeleteVideo: boolean;
  handleToggleAutoDelete: (v: boolean) => void;
  exportFormat: string;
  handleChangeExportFormat: (v: string) => void;
  transcriptOutputDir: string;
  setTranscriptOutputDir: (v: string) => void;
  handleSaveTranscriptOutputDir: () => void;
  youtubeProxy: string;
  setYoutubeProxy: (v: string) => void;
  handleSaveYoutubeProxy: () => void;
  bilibiliProxy: string;
  setBilibiliProxy: (v: string) => void;
  handleSaveBilibiliProxy: () => void;
}

export function PreferenceSettingsSection({
  autoTranscribe,
  handleToggleAutoTranscribe,
  autoDeleteVideo,
  handleToggleAutoDelete,
  exportFormat,
  handleChangeExportFormat,
  transcriptOutputDir,
  setTranscriptOutputDir,
  handleSaveTranscriptOutputDir,
  youtubeProxy,
  setYoutubeProxy,
  handleSaveYoutubeProxy,
  bilibiliProxy,
  setBilibiliProxy,
  handleSaveBilibiliProxy,
}: PreferenceSettingsSectionProps) {
  const EXPORT_FORMATS = [
    { value: 'md', label: 'Markdown' },
    { value: 'docx', label: 'Word' },
    { value: 'pdf', label: 'PDF' },
    { value: 'srt', label: 'SRT' },
    { value: 'txt', label: '纯文本' },
  ] as const;

  return (
    <SettingsGroup title="偏好">
      <SettingsItem
        icon={<Zap className="w-4 h-4 text-ok" />}
        iconBg="bg-ok/10"
        label="自动转写"
        value={<Switch checked={autoTranscribe} onCheckedChange={handleToggleAutoTranscribe} />}
      />
      <SettingsItem
        icon={<Trash2 className="w-4 h-4 text-err" />}
        iconBg="bg-err/10"
        label="转写后删除视频"
        value={<Switch checked={autoDeleteVideo} onCheckedChange={handleToggleAutoDelete} />}
      />
      <SettingsItem
        icon={<FileText className="w-4 h-4 text-warn" />}
        iconBg="bg-warn/10"
        label="导出格式"
        value={EXPORT_FORMATS.find(f => f.value === exportFormat)?.label || exportFormat}
      >
        <div className="pt-3 grid grid-cols-3 gap-2">
          {EXPORT_FORMATS.map((fmt) => (
            <button
              key={fmt.value}
              onClick={() => handleChangeExportFormat(fmt.value)}
              className={cn(
                "px-3 py-2 rounded-lg text-sm font-medium transition-all",
                exportFormat === fmt.value
                  ? "bg-accent text-white"
                  : "bg-sunken text-fg-primary hover:bg-black/[0.04]"
              )}
            >
              {fmt.label}
            </button>
          ))}
        </div>
      </SettingsItem>
      <SettingsItem
        icon={<FileText className="w-4 h-4 text-ok" />}
        iconBg="bg-ok/10"
        label="转写输出目录"
        value={transcriptOutputDir || '默认'}
      >
        <div className="pt-3 space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="留空使用默认目录"
              value={transcriptOutputDir}
              onChange={(e) => setTranscriptOutputDir(e.target.value)}
              className="flex-1 bg-sunken rounded-lg px-3 py-2 text-sm text-fg-primary outline-none border border-transparent focus:border-accent-dim transition-colors"
            />
            <button
              onClick={handleSaveTranscriptOutputDir}
              className="px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:brightness-110 transition-all active:scale-[0.96]"
            >
              保存
            </button>
          </div>
          <div className="text-xs text-fg-muted">
            默认位置：项目根目录下的 transcripts 文件夹
          </div>
        </div>
      </SettingsItem>
      <SettingsItem
        icon={<Globe className="w-4 h-4 text-warn" />}
        iconBg="bg-warn/10"
        label="YouTube 代理"
        value={youtubeProxy || '无代理（或直连）'}
      >
        <div className="pt-3 space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="e.g. http://127.0.0.1:7890"
              value={youtubeProxy}
              onChange={(e) => setYoutubeProxy(e.target.value)}
              className="flex-1 bg-sunken rounded-lg px-3 py-2 text-sm text-fg-primary outline-none border border-transparent focus:border-accent-dim transition-colors"
            />
            <button
              onClick={handleSaveYoutubeProxy}
              className="px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:brightness-110 transition-all active:scale-[0.96]"
            >
              保存
            </button>
          </div>
          <div className="text-xs text-fg-muted">
            留空将依次尝试系统环境变量 YOUTUBE_PROXY 或 BILIBILI_PROXY。
          </div>
        </div>
      </SettingsItem>
      <SettingsItem
        icon={<Globe className="w-4 h-4 text-warn" />}
        iconBg="bg-warn/10"
        label="B 站代理"
        value={bilibiliProxy || '无代理（或直连）'}
      >
        <div className="pt-3 space-y-3">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="e.g. http://127.0.0.1:7890"
              value={bilibiliProxy}
              onChange={(e) => setBilibiliProxy(e.target.value)}
              className="flex-1 bg-sunken rounded-lg px-3 py-2 text-sm text-fg-primary outline-none border border-transparent focus:border-accent-dim transition-colors"
            />
            <button
              onClick={handleSaveBilibiliProxy}
              className="px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:brightness-110 transition-all active:scale-[0.96]"
            >
              保存
            </button>
          </div>
          <div className="text-xs text-fg-muted">
            留空将使用系统环境变量 BILIBILI_PROXY。
          </div>
        </div>
      </SettingsItem>
    </SettingsGroup>
  );
}
