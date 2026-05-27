import { useEffect, useMemo, useRef, useState, useCallback, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import {
  Download, ChevronLeft, ChevronRight, Type, List,
  Star, ArrowLeft, ExternalLink, Search, X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { markAsset, exportTranscripts, getAssetFileUrl } from '@/lib/api';
import type { Asset } from '@/types';

// 用 pdfjs-dist 自带 worker（react-pdf v10 推荐方式）
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

interface Heading {
  level: number;
  text: string;
  id: string;
}

/* Icon button — editorial */
const IconBtn = ({ onClick, title, active, disabled, children }: {
  onClick?: () => void; title: string; active?: boolean; disabled?: boolean; children: ReactNode;
}) => (
  <button
    onClick={onClick}
    disabled={disabled}
    title={title}
    className={cn(
      'w-9 h-9 flex items-center justify-center rounded-lg border border-transparent transition-all duration-200',
      active
        ? 'text-[var(--color-rust)] bg-[rgba(99,102,241,0.08)] border-[var(--color-rust)]/25'
        : 'text-[var(--color-ash)] hover:text-[var(--color-bone)] hover:bg-white/5 hover:border-white/5',
      disabled && 'opacity-30 cursor-not-allowed'
    )}
  >
    {children}
  </button>
);

interface TranscriptReaderProps {
  asset: Asset;
  content: string;
  loading: boolean;
  format?: 'markdown' | 'text';
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
  onAssetUpdate?: (asset: Asset) => void;
}

const FONT_SIZES = [
  { label: '小', size: 14, lineHeight: 1.65 },
  { label: '中', size: 16, lineHeight: 1.75 },
  { label: '大', size: 18, lineHeight: 1.85 },
  { label: '特大', size: 20, lineHeight: 1.9 },
];

export function TranscriptReader({
  asset,
  content,
  loading,
  format = 'markdown',
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

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<number[]>([]);
  const [currentSearchIndex, setCurrentSearchIndex] = useState(0);
  const [searchOpen, setSearchOpen] = useState(false);

  const fontSize = FONT_SIZES[fontSizeIndex];

  // PDF 走原生浏览器 viewer：保留分页/字体/搜索/选择，比"提取文本+自定义渲染"高保真很多
  const isPdf = (asset.transcript_path || '').toLowerCase().endsWith('.pdf');

  const headings = useMemo(() => {
    const h: Heading[] = [];
    let idx = 0;
    const lines = content.split('\n');
    for (const line of lines) {
      const match = line.match(/^(#{1,6})\s+(.+)$/);
      if (match) {
        h.push({ level: match[1].length, text: match[2].trim(), id: `heading-${idx++}` });
      }
    }
    return h;
  }, [content]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const scrollTop = el.scrollTop;
      const scrollHeight = el.scrollHeight - el.clientHeight;
      setProgress(scrollHeight > 0 ? Math.min(100, (scrollTop / scrollHeight) * 100) : 0);

      const headingEls = el.querySelectorAll('[data-heading-id]');
      let closest: string | null = null;
      let closestDist = Infinity;
      for (const h of headingEls) {
        const dist = Math.abs((h as HTMLElement).offsetTop - scrollTop - 80);
        if (dist < closestDist) { closestDist = dist; closest = h.getAttribute('data-heading-id'); }
      }
      setActiveHeading(closest);
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => el.removeEventListener('scroll', onScroll);
  }, [content]);

  useEffect(() => {
    if (!asset.is_read && !isRead) {
      markAsset(asset.asset_id, { is_read: true }).then(() => {
        setIsRead(true);
        onAssetUpdate?.({ ...asset, is_read: true });
      }).catch((err) => {
        console.error('Failed to mark asset as read', err);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally runs only on asset_id change
  }, [asset.asset_id]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (searchOpen) { setSearchOpen(false); setSearchQuery(''); return; }
        e.preventDefault(); onClose();
      }
      if (e.key === 'ArrowLeft' && (e.metaKey || e.ctrlKey) && hasPrev) { e.preventDefault(); onPrev?.(); }
      if (e.key === 'ArrowRight' && (e.metaKey || e.ctrlKey) && hasNext) { e.preventDefault(); onNext?.(); }
      if ((e.key === 'f' || e.key === 'F') && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setSearchOpen(true);
        setTimeout(() => document.getElementById('transcript-search-input')?.focus(), 50);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose, onPrev, onNext, hasPrev, hasNext, searchOpen]);

  useEffect(() => {
    const lines = content.split('\n');
    const results: number[] = [];
    lines.forEach((line, idx) => {
      if (line.toLowerCase().includes(searchQuery.toLowerCase())) results.push(idx);
    });
    setSearchResults(results);
    setCurrentSearchIndex(0);
  }, [searchQuery, content]);

  const handleToggleStar = useCallback(async () => {
    const newVal = !isStarred;
    try {
      await markAsset(asset.asset_id, { is_starred: newVal });
      setIsStarred(newVal);
      onAssetUpdate?.({ ...asset, is_starred: newVal });
      toast.success(newVal ? '已收藏' : '已取消收藏');
    } catch { toast.error('操作失败'); }
  }, [isStarred, asset, onAssetUpdate]);

  const handleExport = useCallback(async () => {
    try { await exportTranscripts([asset.asset_id]); toast.success('导出已开始'); }
    catch { toast.error('导出失败'); }
  }, [asset.asset_id]);

  const handleViewFile = useCallback(() => {
    const url = getAssetFileUrl(asset.asset_id);
    window.open(url, '_blank');
  }, [asset.asset_id]);

  const goToSearchResult = useCallback((direction: 'next' | 'prev') => {
    if (searchResults.length === 0) return;
    const newIndex = direction === 'next'
      ? (currentSearchIndex + 1) % searchResults.length
      : (currentSearchIndex - 1 + searchResults.length) % searchResults.length;
    setCurrentSearchIndex(newIndex);
    const lineIdx = searchResults[newIndex];
    const lines = scrollRef.current?.querySelectorAll('[data-line]');
    if (lines && lines[lineIdx]) {
      (lines[lineIdx] as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [searchResults, currentSearchIndex]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
      className="fixed inset-0 z-50 flex flex-col bg-[var(--color-ink)]"
    >
      {/* ═══ TOP BAR ════════════════════════════════════════════ */}
      <div className="shrink-0 flex items-center justify-between px-6 h-14 border-b border-[var(--color-hairline)] bg-[var(--color-paper)]/60 backdrop-blur-xl">
        <div className="flex items-center gap-4 min-w-0">
          <button
            onClick={onClose}
            className="flex items-center gap-2 text-[12px] text-[var(--color-ash)] hover:text-[var(--color-rust)] transition-colors"
            title="返回 (Esc)"
          >
            <ArrowLeft className="w-3.5 h-3.5" strokeWidth={1.5} />
            <span>返回</span>
          </button>
          <div className="w-px h-4 bg-[var(--color-hairline-strong)]" />
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[13px] text-[var(--color-bone)] truncate max-w-[280px] sm:max-w-[440px]">
              {asset.title || '未命名'}
            </span>
            {isStarred && (
              <Star className="w-3 h-3 text-[var(--color-ember)] fill-[var(--color-ember)] flex-shrink-0" />
            )}
          </div>
        </div>

        <div className="flex items-center gap-1">
          {/* Inline search input */}
          {searchOpen ? (
            <div className="flex items-center gap-2 px-3 h-9 border-b border-[var(--color-rust)] bg-[var(--color-vellum)]/50">
              <Search className="w-3.5 h-3.5 text-[var(--color-smoke)]" strokeWidth={1.5} />
              <input
                id="transcript-search-input"
                type="text"
                placeholder="搜索文稿..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-40 bg-transparent text-[13px] text-[var(--color-bone)] placeholder:text-[var(--color-smoke)] outline-none"
              />
              {searchQuery && searchResults.length > 0 && (
                <span className="font-mono text-[10px] text-[var(--color-ash)] tabular">
                  {currentSearchIndex + 1}/{searchResults.length}
                </span>
              )}
              {searchQuery && searchResults.length > 0 && (
                <>
                  <button onClick={() => goToSearchResult('prev')} className="text-[var(--color-ash)] hover:text-[var(--color-rust)] text-[10px]">▲</button>
                  <button onClick={() => goToSearchResult('next')} className="text-[var(--color-ash)] hover:text-[var(--color-rust)] text-[10px]">▼</button>
                </>
              )}
              <button onClick={() => { setSearchOpen(false); setSearchQuery(''); }} className="text-[var(--color-smoke)] hover:text-[var(--color-rust)]">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <IconBtn onClick={() => { setSearchOpen(true); setTimeout(() => document.getElementById('transcript-search-input')?.focus(), 50); }} title="搜索 (⌘F)">
              <Search className="w-4 h-4" strokeWidth={1.5} />
            </IconBtn>
          )}

          {hasPrev !== undefined && (
            <>
              <IconBtn onClick={onPrev} disabled={!hasPrev} title="上一篇 (⌘←)">
                <ChevronLeft className="w-4 h-4" strokeWidth={1.5} />
              </IconBtn>
              <IconBtn onClick={onNext} disabled={!hasNext} title="下一篇 (⌘→)">
                <ChevronRight className="w-4 h-4" strokeWidth={1.5} />
              </IconBtn>
              <div className="w-px h-4 bg-[var(--color-hairline-strong)] mx-1" />
            </>
          )}

          <IconBtn onClick={handleToggleStar} title={isStarred ? '取消收藏' : '收藏'} active={isStarred}>
            <Star className={cn('w-4 h-4', isStarred && 'fill-[var(--color-ember)] text-[var(--color-ember)]')} strokeWidth={1.5} />
          </IconBtn>

          {headings.length > 0 && (
            <IconBtn onClick={() => setShowToc((v) => !v)} title="目录" active={showToc}>
              <List className="w-4 h-4" strokeWidth={1.5} />
            </IconBtn>
          )}

          <IconBtn onClick={() => setFontSizeIndex((i) => (i + 1) % FONT_SIZES.length)} title={`字号 · ${fontSize.label}`}>
            <Type className="w-4 h-4" strokeWidth={1.5} />
          </IconBtn>

          {asset.transcript_path && (
            <IconBtn onClick={handleViewFile} title="查看原文件">
              <ExternalLink className="w-4 h-4" strokeWidth={1.5} />
            </IconBtn>
          )}

          <IconBtn onClick={handleExport} title="导出">
            <Download className="w-4 h-4" strokeWidth={1.5} />
          </IconBtn>
        </div>
      </div>

      {/* ═══ PROGRESS HAIRLINE ══════════════════════════════════ */}
      <div className="shrink-0 h-px bg-[var(--color-hairline-faint)] relative overflow-hidden">
        <motion.div
          className="absolute inset-y-0 left-0 bg-[var(--color-rust)]"
          style={{ width: `${progress}%` }}
          transition={{ duration: 0.1 }}
        />
      </div>

      {/* ═══ MAIN ═══════════════════════════════════════════════ */}
      <div className="flex-1 flex min-h-0">
        {/* TOC */}
        <AnimatePresence>
          {showToc && headings.length > 0 && (
            <motion.aside
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 260, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 400, damping: 35 }}
              className="shrink-0 border-r border-[var(--color-hairline)] bg-[var(--color-paper)]/40 overflow-hidden"
            >
              <div className="w-[260px] h-full overflow-y-auto px-6 py-7">
                <div className="eyebrow mb-4">目录</div>
                <nav className="space-y-1">
                  {headings.map((h) => (
                    <button
                      key={h.id}
                      onClick={() => document.getElementById(h.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                      className={cn(
                        'w-full text-left py-1.5 text-[13px] leading-snug transition-colors border-l-2',
                        activeHeading === h.id
                          ? 'text-[var(--color-rust)] border-[var(--color-rust)]'
                          : 'text-[var(--color-ash)] hover:text-[var(--color-bone)] border-transparent'
                      )}
                      style={{ paddingLeft: `${10 + (h.level - 1) * 12}px` }}
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
        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-24">
              <div className="flex flex-col items-center gap-3">
                <div className="w-5 h-5 rounded-full border border-[var(--color-hairline-strong)] border-t-[var(--color-rust)] animate-spin" />
                <span className="mono-cap">加载中</span>
              </div>
            </div>
          ) : isPdf ? (
            // PDF：用 react-pdf (PDF.js) 在网页内 canvas 渲染，沿用站点设计语言
            <PdfPagedReader url={getAssetFileUrl(asset.asset_id)} title={asset.title || 'Transcript'} />
          ) : (
            <article
              className="max-w-[680px] mx-auto px-8 sm:px-12 py-14 sm:py-20"
              style={{ fontSize: fontSize.size, lineHeight: fontSize.lineHeight }}
            >
              {/* Title block */}
              <header className="mb-12 pb-8 border-b border-[var(--color-hairline)]">
                <div className="eyebrow mb-4">
                  {asset.create_time
                    ? new Date(asset.create_time).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
                    : '未知日期'
                  }
                </div>
                <h1 className="font-display text-[clamp(32px,4vw,52px)] leading-[1.1] tracking-display text-[var(--color-bone)]">
                  {asset.title || '未命名'}
                </h1>
              </header>

              {/* Content */}
              <div className="text-[var(--color-bone)] prose prose-invert max-w-none
                            prose-headings:font-display prose-headings:font-normal prose-headings:text-[var(--color-bone)]
                            prose-h1:text-[1.6em] prose-h2:text-[1.35em] prose-h3:text-[1.15em]
                            prose-p:text-[var(--color-bone)] prose-p:my-[0.9em] prose-p:leading-[inherit]
                            prose-strong:text-[var(--color-bone)] prose-strong:font-semibold
                            prose-em:text-[var(--color-ash)]
                            prose-a:text-[var(--color-rust)] prose-a:no-underline hover:prose-a:underline
                            prose-blockquote:border-l-[var(--color-rust)] prose-blockquote:text-[var(--color-ash)]
                            prose-code:text-[var(--color-rust)] prose-code:bg-[var(--color-vellum)] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-none prose-code:font-mono prose-code:text-[0.9em]
                            prose-pre:bg-[var(--color-vellum)] prose-pre:border prose-pre:border-[var(--color-hairline)]
                            prose-hr:border-[var(--color-hairline)]
                            prose-li:text-[var(--color-bone)] prose-ul:my-[0.9em] prose-ol:my-[0.9em]">
                {format === 'markdown' ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                ) : (
                  <div className="whitespace-pre-wrap font-sans">
                    {content.split('\n').map((line, i) => {
                      const trimmed = line.trim();
                      const isSpeaker = /^(发言人|Speaker|嘉宾)/.test(trimmed);
                      const isTimestamp = /^\d{2}:\d{2}/.test(trimmed);
                      const isHeader = /原文$/.test(trimmed);
                      const isMatch = searchResults.includes(i);
                      return (
                        <div key={i} data-line={i} className={cn(
                          isMatch && 'bg-[rgba(212,168,80,0.18)] -mx-2 px-2',
                          isSpeaker && 'mt-5 mb-1 text-[var(--color-rust)] font-medium text-[0.9em]',
                          isTimestamp && 'text-[var(--color-smoke)] text-[0.78em] font-mono',
                          isHeader && 'eyebrow mt-8 mb-4 pb-3 border-b border-[var(--color-hairline)]',
                          !isSpeaker && !isTimestamp && !isHeader && 'text-[var(--color-bone)]',
                        )}>
                          {line}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="h-24" />
              <div className="mono-cap text-center pt-6 border-t border-[var(--color-hairline-faint)]">
                ⸺ 全文完 ⸺
              </div>
            </article>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════════════════
 *  PdfPagedReader — 在网页内用 PDF.js 渲染所有页面，保留站点设计语言。
 *  全部页面纵向滚动展示，支持文本选中/复制（pdfjs textLayer 提供）。
 * ═══════════════════════════════════════════════════════════════ */
function PdfPagedReader({ url, title }: { url: string; title: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [numPages, setNumPages] = useState<number>(0);
  const [pageWidth, setPageWidth] = useState<number>(720);
  const [error, setError] = useState<string | null>(null);

  // 响应容器宽度，让每页 canvas 自适应
  useEffect(() => {
    const update = () => {
      if (containerRef.current) {
        const w = Math.min(containerRef.current.clientWidth - 64, 920);
        setPageWidth(Math.max(420, w));
      }
    };
    update();
    const obs = new ResizeObserver(update);
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  const pdfFile = useMemo(() => ({ url }), [url]);

  return (
    <div ref={containerRef} className="w-full h-full flex flex-col items-center px-4 py-8 overflow-y-auto bg-[var(--color-ink)]">
      <Document
        file={pdfFile}
        onLoadSuccess={({ numPages }) => setNumPages(numPages)}
        onLoadError={(e) => setError(e?.message || 'PDF 加载失败')}
        loading={
          <div className="flex items-center gap-3 py-24 text-[var(--color-smoke)]">
            <div className="w-5 h-5 rounded-full border border-[var(--color-hairline-strong)] border-t-[var(--color-rust)] animate-spin" />
            <span className="mono-cap">PDF 加载中</span>
          </div>
        }
        error={
          <div className="py-24 text-center text-[var(--color-iron)]">
            <div className="mono-cap mb-2">无法加载 PDF</div>
            <div className="text-[12px] text-[var(--color-smoke)]">{error || '请检查文件是否存在'}</div>
          </div>
        }
        className="flex flex-col items-center gap-5"
      >
        {/* 顶部 PDF 标题（与页面其他部分一致风格） */}
        {numPages > 0 && (
          <div className="w-full max-w-[920px] mb-2 pb-3 border-b border-[var(--color-hairline)] text-center">
            <div className="eyebrow">{numPages} 页 · PDF</div>
          </div>
        )}

        {Array.from(new Array(numPages), (_, idx) => (
          <div
            key={`page_${idx + 1}`}
            className="shadow-[0_8px_30px_rgba(0,0,0,0.4)] border border-[var(--color-hairline-faint)] bg-white rounded-sm overflow-hidden"
          >
            <Page
              pageNumber={idx + 1}
              width={pageWidth}
              renderTextLayer
              renderAnnotationLayer={false}
              loading={
                <div
                  style={{ width: pageWidth, height: pageWidth * 1.414 }}
                  className="bg-[var(--color-paper)] animate-pulse"
                />
              }
            />
          </div>
        ))}

        {numPages > 0 && (
          <div className="mono-cap text-[var(--color-smoke)] py-8">
            ⸺ {title} · 共 {numPages} 页 ⸺
          </div>
        )}
      </Document>
    </div>
  );
}
