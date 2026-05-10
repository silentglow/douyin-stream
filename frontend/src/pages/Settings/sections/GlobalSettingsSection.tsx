import { Loader2, Trash2, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent } from '@/components/ui/card';
import { toast } from 'sonner';
import { cleanupMissingAssets } from '@/lib/api';
import { useStore } from '@/store/useStore';
import { cn } from '@/lib/utils';

interface GlobalSettingsSectionProps {
  autoTranscribe: boolean;
  onToggleAutoTranscribe: (value: boolean) => void;
  autoDeleteVideo: boolean;
  onToggleAutoDelete: (value: boolean) => void;
  concurrency: number;
  setConcurrency: (v: number) => void;
  isSavingConcurrency: boolean;
  onSaveConcurrency: () => void;
  exportFormat: string;
  onChangeExportFormat: (format: string) => void;
  refreshSettings: () => void;
}

const EXPORT_FORMATS = [
  { value: 'md', label: 'MD', description: 'Markdown' },
  { value: 'docx', label: 'DOCX', description: 'Word 文档' },
  { value: 'pdf', label: 'PDF', description: 'PDF 文档' },
  { value: 'srt', label: 'SRT', description: '字幕文件' },
  { value: 'txt', label: 'TXT', description: '纯文本' },
] as const;

export function GlobalSettingsSection({
  autoTranscribe,
  onToggleAutoTranscribe,
  autoDeleteVideo,
  onToggleAutoDelete,
  concurrency,
  setConcurrency,
  isSavingConcurrency,
  onSaveConcurrency,
  exportFormat,
  onChangeExportFormat,
  refreshSettings,
}: GlobalSettingsSectionProps) {
  return (
    <Card size="default" className="w-full">
      <CardContent className="space-y-4">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="size-9 rounded-[10px] bg-gradient-to-br from-primary/15 to-primary/5 flex items-center justify-center">
            <Settings2 className="size-5 text-primary" />
          </div>
          <div>
            <h3 className="text-title-3 font-semibold text-foreground">全局参数</h3>
            <p className="text-caption text-muted-foreground">下载后的自动化行为和并发控制。</p>
          </div>
        </div>

        {/* Export Format */}
        <div className="apple-list-item rounded-[10px] px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-body font-medium text-foreground">导出格式</div>
              <div className="text-caption text-muted-foreground">转写文稿的输出格式，新转写将使用此格式。</div>
            </div>
            <div className="flex items-center gap-1 rounded-lg bg-muted p-0.5">
              {EXPORT_FORMATS.map((fmt) => (
                <button
                  key={fmt.value}
                  type="button"
                  onClick={() => onChangeExportFormat(fmt.value)}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-[13px] font-medium transition-all duration-150',
                    exportFormat === fmt.value
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  {fmt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Auto Transcribe */}
        <div className="apple-list-item rounded-[10px] px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-body font-medium text-foreground">自动转写</div>
              <div className="text-caption text-muted-foreground">下载完成后自动调用 Qwen 转写。</div>
            </div>
            <Switch checked={autoTranscribe} onCheckedChange={onToggleAutoTranscribe} />
          </div>
        </div>

        {/* Auto Delete */}
        <div className="apple-list-item rounded-[10px] px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-body font-medium text-foreground">自动删除源视频</div>
              <div className="text-caption text-muted-foreground">转写完成后自动删除原始视频文件。</div>
            </div>
            <Switch checked={autoDeleteVideo} onCheckedChange={onToggleAutoDelete} />
          </div>
        </div>

        {/* Concurrency */}
        <div className="apple-list-item rounded-[10px] px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-body font-medium text-foreground">并发数</div>
              <div className="text-caption text-muted-foreground">建议 3，确认稳定后可提高。</div>
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={concurrency.toString()}
                onChange={(e) => {
                  const val = parseInt(e.target.value, 10) || 1;
                  setConcurrency(Math.min(10, Math.max(1, val)));
                }}
                className="w-16 text-center"
              />
            </div>
          </div>
        </div>

        {/* Cleanup */}
        <div className="apple-list-item rounded-[10px] px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-body font-medium text-foreground">清理不存在素材</div>
              <div className="text-caption text-muted-foreground">删除本地文件已被删除的素材记录。</div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                try {
                  const result = await cleanupMissingAssets();
                  toast.success(`已清理 ${result.deleted} 条无效记录`);
                  useStore.getState().fetchCreators(true); 
                  refreshSettings();
                } catch {
                  // interceptor already toasts;
                }
              }}
              className="text-destructive hover:text-destructive"
            >
              <Trash2 className="size-3.5" />
              <span className="text-[13px]">清理</span>
            </Button>
          </div>
        </div>

        {/* Save Button */}
        <div className="pt-2">
          <Button
            variant="primary"
            onClick={onSaveConcurrency}
            disabled={isSavingConcurrency}
          >
            {isSavingConcurrency && <Loader2 className="size-4 animate-spin" />}
            保存并发设置
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
