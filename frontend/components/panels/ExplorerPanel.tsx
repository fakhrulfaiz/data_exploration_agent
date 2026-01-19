'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import StepDetails from '@/components/StepDetails';
import { StepExplanation } from '@/types/chat';
import { getStatusDisplayName, getStatusColor } from '@/utils/statusHelpers';
import { markdownComponents } from '@/utils/markdownComponents';
import remarkGfm from 'remark-gfm';
import { Sheet, SheetContent } from '@/components/ui/sheet';

export type ExplorerResult = {
  thread_id: string;
  run_status: string;
  assistant_response?: string;
  query?: string;
  plan?: string;
  error?: string | null;
  steps?: StepExplanation[];
  final_result?: {
    summary?: string;
    details?: string;
    source?: string;
    inference?: string;
    extra_explanation?: string;
  };
  total_time?: number | null;
  overall_confidence?: number;
};

type ExplorerPanelProps = {
  open: boolean;
  onClose: () => void;
  data: ExplorerResult | null;
  initialWidthPx?: number;
  minWidthPx?: number;
  maxWidthPx?: number;
  onSuggestionClick?: (query: string) => void; // Add callback for suggestion clicks
};

const ExplorerPanel: React.FC<ExplorerPanelProps> = ({
  open,
  onClose,
  data,
  initialWidthPx = 620,
  minWidthPx = 320,
  maxWidthPx = 1100,
  onSuggestionClick,
}) => {
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [selectedQuery, setSelectedQuery] = useState<string>('');


  const getResponsiveWidth = () => {
    const screenWidth = typeof window !== 'undefined' ? window.innerWidth : initialWidthPx;
    if (screenWidth <= 768) {
      return Math.min(screenWidth, maxWidthPx);
    } else if (screenWidth <= 1024) {
      return Math.min(screenWidth * 0.8, initialWidthPx);
    }
    return initialWidthPx;
  };

  const getIsMobile = () => (typeof window !== 'undefined' ? window.innerWidth <= 768 : false);

  // Initialize with fixed values to prevent hydration mismatch
  const [width, setWidth] = useState<number>(initialWidthPx);
  const [isMobile, setIsMobile] = useState<boolean>(false);
  const [isHydrated, setIsHydrated] = useState(false);

  // Set responsive values after hydration
  useEffect(() => {
    setIsHydrated(true);
    setWidth(getResponsiveWidth());
    setIsMobile(getIsMobile());
  }, []);
  const isResizingRef = useRef<boolean>(false);

  const onMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isResizingRef.current) return;
      const newWidth = Math.min(
        Math.max(window.innerWidth - e.clientX, minWidthPx),
        maxWidthPx,
      );
      setWidth(newWidth);
    },
    [minWidthPx, maxWidthPx],
  );

  const handleWindowResize = useCallback(() => {
    if (!isResizingRef.current) {
      setWidth(getResponsiveWidth());
    }
    setIsMobile(getIsMobile());
  }, []);

  const onMouseUp = useCallback(() => {
    isResizingRef.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  const startResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('resize', handleWindowResize);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('resize', handleWindowResize);
    };
  }, [onMouseMove, onMouseUp, handleWindowResize]);

  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <SheetContent
        side="right"
        hideCloseButton
        className="p-0 h-full max-w-full w-full shadow-xl border-l border-gray-200 dark:border-neutral-700 bg-white dark:bg-neutral-900"
        style={{
          width: isMobile ? '100%' : width,
          minWidth: isMobile ? undefined : minWidthPx,
          maxWidth: isMobile ? '100%' : maxWidthPx,
        }}
      >
        <div
          onMouseDown={startResize}
          className="absolute left-0 top-0 h-full w-1 cursor-col-resize bg-transparent hover:bg-gray-200/50 hidden sm:block"
          aria-label="Resize"
        />

        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-900">
          <h3 className="font-semibold text-gray-900 dark:text-white">Agent Explorer</h3>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-3 py-2 rounded bg-gray-200 dark:bg-neutral-700 hover:bg-gray-300 dark:hover:bg-neutral-600 text-gray-800 dark:text-white text-sm sm:text-sm min-h-[36px] touch-manipulation"
              aria-label="Close panel"
            >
              Close
            </button>
          </div>
        </div>

        <div
          className="p-4 h-[calc(100%-56px)] slim-scroll text-gray-900 dark:text-neutral-200 [scrollbar-width:thin] [scrollbar-color:#d1d5db_transparent] dark:[scrollbar-color:#525252_transparent]"
          style={{
            overflowY: 'overlay' as any,
          }}
        >
          {!data ? (
            <div className="text-gray-500 dark:text-neutral-400 text-sm">
              No data yet. Send a message and open after the result.
            </div>
          ) : (
            <div className="space-y-4">
              {data.query && (
                <div className="p-3 bg-blue-50 dark:bg-neutral-800 rounded border border-blue-200 dark:border-neutral-700">
                  <div className="text-sm text-blue-800 dark:text-blue-400 font-medium mb-1">
                    Your Question
                  </div>
                  <div className="text-gray-700 dark:text-neutral-200 text-sm font-medium">
                    {data.query}
                  </div>
                </div>
              )}

              {/* Summary Section - Parse JSON properly */}
              {(() => {
                const summaryText = data.final_result?.summary || data.assistant_response || '';
                let parsedData: { response?: string; actions?: { next_queries?: string[] } } | null = null;
                
                // Try to parse as JSON first
                try {
                  parsedData = JSON.parse(summaryText);
                } catch {
                  // Not JSON, use as plain text
                }
                
                const responseText = parsedData?.response || summaryText;
                const nextQueries = parsedData?.actions?.next_queries || [];
                
                return (
                  <>
                    <details className="border border-green-200 dark:border-neutral-700 rounded bg-green-50 dark:bg-neutral-800" open>
                      <summary className="list-none cursor-pointer select-none p-3 flex items-center justify-between hover:bg-green-100 dark:hover:bg-neutral-700">
                        <div className="text-sm text-gray-800 dark:text-neutral-200 font-medium">Summary</div>
                        <span className="text-xs text-gray-500 dark:text-neutral-400">Click to collapse</span>
                      </summary>
                      <div className="p-3 border-t border-green-200 dark:border-neutral-700 text-gray-700 dark:text-neutral-200 text-sm">
                        {responseText ? (
                          <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
                            {responseText}
                          </ReactMarkdown>
                        ) : (
                          '—'
                        )}
                      </div>
                    </details>
                    
                    {/* Next Query Suggestions */}
                    {nextQueries.length > 0 && (
                      <div className="animate-in fade-in slide-in-from-bottom-2 duration-500 p-3 bg-blue-50 dark:bg-neutral-800 rounded border border-blue-200 dark:border-neutral-700">
                        <div className="flex items-center gap-2 mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
                          </svg>
                          Suggested Next Steps
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {nextQueries.map((query, idx) => (
                            <button
                              key={idx}
                              onClick={() => {
                                setSelectedQuery(query);
                                setShowConfirmDialog(true);
                              }}
                              className="text-left text-sm px-3 py-1.5 rounded-full bg-blue-100 dark:bg-neutral-700 hover:bg-blue-200 dark:hover:bg-neutral-600 text-blue-800 dark:text-blue-200 border border-blue-200 dark:border-neutral-600 hover:border-blue-300 dark:hover:border-neutral-500 transition-all duration-200 cursor-pointer"
                            >
                              {query}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                );
              })()}

              {data.plan && (
                <details className="border border-blue-200 dark:border-neutral-700 rounded bg-blue-50 dark:bg-neutral-800">
                  <summary className="list-none cursor-pointer select-none p-3 flex items-center justify-between hover:bg-blue-100 dark:hover:bg-neutral-700">
                    <div className="text-base text-gray-800 dark:text-neutral-200 font-medium">Plan</div>
                    <span className="text-sm text-gray-500 dark:text-neutral-400">Click to expand</span>
                  </summary>
                  <div className="p-3 border-t border-blue-200 dark:border-neutral-700 text-sm text-gray-700 dark:text-neutral-200">
                    <ReactMarkdown components={markdownComponents}>
                      {data.plan}
                    </ReactMarkdown>
                  </div>
                </details>
              )}

              {data.final_result?.details && (
                <div className="p-3 bg-gray-50 dark:bg-neutral-800 rounded border border-gray-200 dark:border-neutral-700">
                  <div className="text-base text-gray-800 dark:text-neutral-200 font-medium mb-1">
                    Details
                  </div>
                  <div className="text-sm text-gray-700 dark:text-neutral-200">
                    <ReactMarkdown components={markdownComponents}>
                      {data.final_result.details}
                    </ReactMarkdown>
                  </div>
                </div>
              )}

              <StepDetails steps={data.steps || []} />

              <div className="grid grid-cols-2 gap-2 text-xs text-gray-700 dark:text-neutral-200">
                <div className="p-2 bg-gray-50 dark:bg-neutral-800 rounded border border-gray-200 dark:border-neutral-700">
                  <div className="text-gray-500 dark:text-neutral-400">Execution Status</div>
                  <div className={`font-medium px-2 py-1 rounded text-xs ${getStatusColor(data.run_status)}`}>
                    {getStatusDisplayName(data.run_status)}
                  </div>
                </div>
                <div className="p-2 bg-gray-50 dark:bg-neutral-800 rounded border border-gray-200 dark:border-neutral-700">
                  <div className="text-gray-500 dark:text-neutral-400">Confidence</div>
                  <div className="font-medium">
                    {typeof data.overall_confidence === 'number'
                      ? `${(data.overall_confidence * 100).toFixed(0)}%`
                      : '—'}
                  </div>
                </div>
                <div className="p-2 bg-gray-50 dark:bg-neutral-800 rounded border border-gray-200 dark:border-neutral-700">
                  <div className="text-gray-500 dark:text-neutral-400">Total time</div>
                  <div className="font-medium">
                    {typeof data.total_time === 'number' ? `${data.total_time.toFixed(2)}s` : '—'}
                  </div>
                </div>
                <div className="p-2 bg-gray-50 dark:bg-neutral-800 rounded border border-gray-200 dark:border-neutral-700">
                  <div className="text-gray-500 dark:text-neutral-400">Thread</div>
                  <div className="font-medium">{data.thread_id}...</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </SheetContent>
      
      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowConfirmDialog(false)}>
          <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl p-6 max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Start New Query?</h3>
            <p className="text-sm text-gray-600 dark:text-neutral-300 mb-4">
              This will clear the current chat and start with:
            </p>
            <div className="p-3 bg-blue-50 dark:bg-neutral-700 rounded border border-blue-200 dark:border-neutral-600 mb-4">
              <p className="text-sm font-medium text-blue-900 dark:text-blue-100">{selectedQuery}</p>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowConfirmDialog(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setShowConfirmDialog(false);
                  onClose();
                  onSuggestionClick?.(selectedQuery);
                }}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded transition-colors"
              >
                Continue
              </button>
            </div>
          </div>
        </div>
      )}
    </Sheet>
  );
};

export default ExplorerPanel;

