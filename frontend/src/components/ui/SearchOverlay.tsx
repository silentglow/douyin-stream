import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, X, FileText, Users, Play, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { globalSearch, type SearchResult } from '@/services/search';
import { cn } from '@/lib/utils';
import { useNavigate } from 'react-router-dom';

interface SearchOverlayProps {
  open: boolean;
  onClose: () => void;
}

const typeIcons = {
  asset: FileText,
  creator: Users,
  task: Play,
};

const typeLabels = {
  asset: '素材',
  creator: '创作者',
  task: '任务',
};

export function SearchOverlay({ open, onClose }: SearchOverlayProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    } else {
      setQuery('');
      setResults([]);
      setSelectedIndex(0);
    }
  }, [open]);

  const doSearch = useCallback(async (q: string) => {
    if (abortRef.current) abortRef.current.abort();
    if (!q.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    try {
      const data = await globalSearch(q.trim(), controller.signal);
      if (!controller.signal.aborted) {
        setResults(data);
        setSelectedIndex(0);
      }
    } catch {
      // ignore abort errors
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => doSearch(query), 200);
    return () => clearTimeout(timer);
  }, [query, doSearch]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && results[selectedIndex]) {
      handleSelect(results[selectedIndex]);
    }
  }, [results, selectedIndex, onClose]);

  const handleSelect = (result: SearchResult) => {
    onClose();
    if (result.type === 'creator') {
      navigate(`/library/${encodeURIComponent(result.id)}`);
    } else if (result.type === 'asset') {
      if (result.creator_uid) {
        navigate(`/library/${encodeURIComponent(result.creator_uid)}`, {
          state: { openAssetId: result.id },
        });
      } else {
        navigate('/library');
      }
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ type: 'spring', stiffness: 500, damping: 35 }}
          className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4"
          onClick={onClose}
        >
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" />
          <motion.div
            initial={{ opacity: 0, y: -20, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            className="relative w-full max-w-xl bg-card rounded-[22px] shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Search Input */}
            <div className="flex items-center gap-3 px-5 py-4 border-b border-border/40">
              {loading ? (
                <Loader2 className="size-5 text-muted-foreground animate-spin shrink-0" />
              ) : (
                <Search className="size-5 text-muted-foreground shrink-0" />
              )}
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="搜索素材、创作者、任务..."
                className="flex-1 bg-transparent text-body outline-none placeholder:text-muted-foreground"
              />
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg hover:bg-secondary transition-colors shrink-0"
              >
                <X className="size-4 text-muted-foreground" />
              </button>
            </div>

            {/* Results */}
            <div className="max-h-[50vh] overflow-y-auto">
              {results.length === 0 && query.trim() && !loading && (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  未找到匹配结果
                </div>
              )}
              {results.map((result, i) => {
                const Icon = typeIcons[result.type] || FileText;
                const isSelected = i === selectedIndex;
                return (
                  <button
                    key={`${result.type}-${result.id}-${i}`}
                    onClick={() => handleSelect(result)}
                    className={cn(
                      'w-full flex items-center gap-3 px-5 py-3 text-left transition-colors',
                      isSelected ? 'bg-primary/8' : 'hover:bg-secondary/50',
                      i > 0 && 'border-t border-border/30'
                    )}
                  >
                    <div className={cn(
                      'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
                      result.type === 'asset' && 'bg-primary/10 text-primary',
                      result.type === 'creator' && 'bg-warning/10 text-warning',
                      result.type === 'task' && 'bg-success/10 text-success',
                    )}>
                      <Icon className="size-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate text-foreground">
                        {result.title || result.nickname || result.description || result.id}
                      </div>
                      {result.highlight && (
                        <div className="text-xs text-muted-foreground truncate">
                          {result.highlight}
                        </div>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0 px-2 py-0.5 bg-secondary rounded-full">
                      {typeLabels[result.type]}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Footer hint */}
            <div className="px-5 py-2 border-t border-border/30 text-xs text-muted-foreground flex items-center gap-3">
              <span>↑↓ 选择</span>
              <span>↵ 打开</span>
              <span>Esc 关闭</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
