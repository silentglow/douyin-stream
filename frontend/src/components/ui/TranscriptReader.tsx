import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Download, ChevronLeft, ChevronRight, Type, List,
  CheckCircle2, Star, StarOff, ArrowLeft, ExternalLink,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { markAsset, exportTranscripts, getAssetFileUrl } from '@/lib/api';
import type { Asset } from '@/types';

/* ── Types ── */
interface Heading {
  level: number;
  text: string;
  id: string;
}

interface TranscriptReaderProps {
  asset: Asset;
  content: string;
  loading: boolean;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
  onAssetUpdate?: (asset: Asset) => void;
}

/* ── Helpers ── */
function parseHeadings(content: string): Heading[] {
  const lines = content.split('\n');
  const headings: Heading[] = [];
  let idx = 0;
  for (const line of lines) {
    const match = line.match(/^(#{1,6})\s+(.+)$/);
    if (match) {
      headings.push({
        level: match[1].length,
        text: match[2].trim(),
        id: `heading-${idx++}`,
      });
    }
  }
  return headings;
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .slice(0, 40);
}

/* ── Font size presets ── */
const FONT_SIZES = [
  { label: '小', size: 14, lineHeight: 1.6 },
  { label: '中', size: 16, lineHeight: 1.7 },
  { label: '大', size: 18, lineHeight: 1.8 },
  { label: '特大', size: 20, lineHeight: 1.9 },
];

/* ── Component ── */
export function TranscriptReader({
  asset,
  content,
  loading,
  onClose,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
  onAssetUpdate,
}: TranscriptReaderProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [fontSizeIndex, setFontSizeIndex] = useState(1);
  const [showToc, setShowToc] = useState(false);
  const [progress, setProgress] = useState(0);
  const [activeHeading, setActiveHeading] = useState<string | null>(null);
  const [isStarred, setIsStarred] = useState(asset.is_starred ?? false);
  const [isRead, setIsRead] = useState(asset.is_read ?? false);

  const fontSize = FONT_SIZES[fontSizeIndex];

  const headings = useMemo(() => parseHeadings(content), [content]);

  /* Scroll progress tracking */
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const scrollTop = el.scrollTop;
      const scrollHeight = el.scrollHeight - el.clientHeight;
      setProgress(scrollHeight > 0 ? Math.min(100, (scrollTop / scrollHeight) * 100) : 0);

      /* Active heading detection */
      const headingEls = el.querySelectorAll('[data-heading-id]');
      let closest: string | null = null;
      let closestDist = Infinity;
      for (const h of headingEls) {
        const dist = Math.abs((h as HTMLElement).offsetTop - scrollTop - 80);
        if (dist < closestDist) {
          closestDist = dist;
          closest = h.getAttribute('data-heading-id');
        }
      }
      setActiveHeading(closest);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => el.removeEventListener('scroll', onScroll);
  }, [content]);

  /* Mark as read on open */
  useEffect(() => {
    if (!asset.is_read && !isRead) {
      markAsset(asset.asset_id, { is_read: true }).then(() => {
        setIsRead(true);
        onAssetUpdate?.({ ...asset, is_read: true });
      }).catch(() => {});
    }
  }, [asset.asset_id]);

  /* Keyboard shortcuts */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
      if (e.key === 'ArrowLeft' && (e.metaKey || e.ctrlKey) && hasPrev) {
        e.preventDefault();
        onPrev?.();
      }
      if (e.key === 'ArrowRight' && (e.metaKey || e.ctrlKey) && hasNext) {
        e.preventDefault();
        onNext?.();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose, onPrev, onNext, hasPrev, hasNext]);

  const handleToggleStar = useCallback(async () => {
    const newVal = !isStarred;
    try {
      await markAsset(asset.asset_id, { is_starred: newVal });
      setIsStarred(newVal);
      onAssetUpdate?.({ ...asset, is_starred: newVal });
      toast.success(newVal ? '已收藏' : '已取消收藏');
    } catch {
      toast.error('操作失败');
    }
  }, [isStarred, asset, onAssetUpdate]);

  const handleExport = useCallback(async () => {
    try {
      await exportTranscripts([asset.asset_id]);
      toast.success('导出已开始');
    } catch {
      toast.error('导出失败');
    }
  }, [asset.asset_id]);

  const handleViewFile = useCallback(() => {
    const url = getAssetFileUrl(asset.asset_id);
    window.open(url, '_blank');
  }, [asset.asset_id]);

  /* Render content with heading IDs */
  const renderedContent = useMemo(() => {
    let headingIdx = 0;
    return content.split('\n').map((line, i) => {
      const match = line.match(/^(#{1,6})\s+(.+)$/);
      if (match) {
        const id = headings[headingIdx]?.id ?? `h-${i}`;
        headingIdx++;
        const level = match[1].length;
        const text = match[2].trim();
        const Tag = `h${level}` as React.ElementType;
        return (
          <Tag
            key={i}
            data-heading-id={id}
            id={slugify(text)}
            className={cn(
              'font-semibold text-foreground scroll-mt-20',
              level === 1 && 'text-[1.4em] mt-8 mb-4',
              level === 2 && 'text-[1.25em] mt-6 mb-3',
              level === 3 && 'text-[1.1em] mt-5 mb-2',
              level >= 4 && 'text-[1em] mt-4 mb-2'
            )}
          >
            {text}
          </Tag>
        );
      }
      if (line.trim() === '') {
        return <div key={i} className="h-3" />;
      }
      return (
        <p key={i} className="mb-3 text-foreground/90">
          {line}
        </p>
      );
    });
  }, [content, headings]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-50 flex flex-col bg-background"
    >
      {/* ── Top Bar ── */}
      <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-border/50 bg-card/80 backdrop-blur-xl">
        <div className="flex items-center gap-2">
          <button
            onClick={onClose}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg hover:bg-secondary transition-colors text-sm text-muted-foreground"
          >
            <ArrowLeft className="size-4" />
            <span className="hidden sm:inline">返回</span>
          </button>
          <div className="h-4 w-px bg-border" />
          <div className="text-sm font-medium truncate max-w-[200px] sm:max-w-[400px]">
            {asset.title || '转写内容'}
          </div>
          {asset.transcript_status === 'COMPLETED' && (
            <CheckCircle2 className="size-4 text-success shrink-0" />
          )}
        </div>

        <div className="flex items-center gap-1">
          {/* Navigation */}
          {hasPrev !== undefined && (
            <>
              <button
                onClick={onPrev}
                disabled={!hasPrev}
                className="p-2 rounded-lg hover:bg-secondary transition-colors disabled:opacity-30"
                title="上一篇 (⌘←)"
              >
                <ChevronLeft className="size-4" />
              </button>
              <button
                onClick={onNext}
                disabled={!hasNext}
                className="p-2 rounded-lg hover:bg-secondary transition-colors disabled:opacity-30"
                title="下一篇 (⌘→)"
              >
                <ChevronRight className="size-4" />
              </button>
              <div className="h-4 w-px bg-border mx-1" />
            </>
          )}

          {/* Star */}
          <button
            onClick={handleToggleStar}
            className="p-2 rounded-lg hover:bg-secondary transition-colors"
            title={isStarred ? '取消收藏' : '收藏'}
          >
            {isStarred ? (
              <Star className="size-4 text-warning fill-warning" />
            ) : (
              <StarOff className="size-4 text-muted-foreground" />
            )}
          </button>

          {/* TOC toggle */}
          {headings.length > 0 && (
            <button
              onClick={() => setShowToc((v) => !v)}
              className={cn(
                'p-2 rounded-lg transition-colors',
                showToc ? 'bg-primary/10 text-primary' : 'hover:bg-secondary text-muted-foreground'
              )}
              title="目录"
            >
              <List className="size-4" />
            </button>
          )}

          {/* Font size */}
          <button
            onClick={() => setFontSizeIndex((i) => (i + 1) % FONT_SIZES.length)}
            className="p-2 rounded-lg hover:bg-secondary transition-colors text-muted-foreground"
            title="调整字号"
          >
            <Type className="size-4" />
          </button>

          {/* View original file */}
          {asset.transcript_path && (
            <button
              onClick={handleViewFile}
              className="p-2 rounded-lg hover:bg-secondary transition-colors text-muted-foreground"
              title="查看原文件"
            >
              <ExternalLink className="size-4" />
            </button>
          )}

          {/* Export */}
          <button
            onClick={handleExport}
            className="p-2 rounded-lg hover:bg-secondary transition-colors text-muted-foreground"
            title="导出"
          >
            <Download className="size-4" />
          </button>
        </div>
      </div>

      {/* ── Progress Bar ── */}
      <div className="shrink-0 h-[2px] bg-secondary overflow-hidden">
        <motion.div
          className="h-full bg-primary"
          style={{ width: `${progress}%` }}
          transition={{ duration: 0.1 }}
        />
      </div>

      {/* ── Main Content Area ── */}
      <div className="flex-1 flex min-h-0">
        {/* TOC Sidebar */}
        <AnimatePresence>
          {showToc && headings.length > 0 && (
            <motion.aside
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 240, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 400, damping: 35 }}
              className="shrink-0 border-r border-border/50 bg-card/50 overflow-hidden"
            >
              <div className="w-[240px] h-full overflow-y-auto p-4">
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                  目录
                </div>
                <nav className="space-y-0.5">
                  {headings.map((h) => (
                    <button
                      key={h.id}
                      onClick={() => {
                        const el = document.getElementById(slugify(h.text));
                        if (el) {
                          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }
                      }}
                      className={cn(
                        'w-full text-left px-2 py-1 rounded-md text-sm transition-colors',
                        activeHeading === h.id
                          ? 'bg-primary/10 text-primary font-medium'
                          : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                      )}
                      style={{ paddingLeft: `${8 + (h.level - 1) * 12}px` }}
                    >
                      {h.text}
                    </button>
                  ))}
                </nav>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Reader */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto"
        >
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
                <span className="text-sm text-muted-foreground">加载中...</span>
              </div>
            </div>
          ) : (
            <article
              className="max-w-2xl mx-auto px-5 py-8 sm:px-8 sm:py-12"
              style={{
                fontSize: fontSize.size,
                lineHeight: fontSize.lineHeight,
              }}
            >
              {/* Title */}
              <h1 className="text-[1.6em] font-bold text-foreground mb-2 leading-tight">
                {asset.title || '转写内容'}
              </h1>
              <div className="flex items-center gap-3 text-sm text-muted-foreground mb-8 pb-6 border-b border-border/50">
                {asset.create_time && (
                  <span>{new Date(asset.create_time).toLocaleDateString('zh-CN')}</span>
                )}
                {asset.is_starred && (
                  <span className="inline-flex items-center gap-1 text-warning">
                    <Star className="size-3 fill-warning" />
                    已收藏
                  </span>
                )}
              </div>

              {/* Content */}
              <div className="text-foreground/90">
                {renderedContent}
              </div>

              {/* Bottom spacer */}
              <div className="h-20" />
            </article>
          )}
        </div>
      </div>
    </motion.div>
  );
}
