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
};

const ExplorerPanel: React.FC<ExplorerPanelProps> = ({
  open,
  onClose,
  data,
  initialWidthPx = 620,
  minWidthPx = 320,
  maxWidthPx = 1100,
}) => {


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

              <details className="border border-green-200 dark:border-neutral-700 rounded bg-green-50 dark:bg-neutral-800">
                <summary className="list-none cursor-pointer select-none p-3 flex items-center justify-between hover:bg-green-100 dark:hover:bg-neutral-700">
                  <div className="text-sm text-gray-800 dark:text-neutral-200 font-medium">Summary</div>
                  <span className="text-xs text-gray-500 dark:text-neutral-400">Click to expand</span>
                </summary>
                <div className="p-3 border-t border-green-200 dark:border-neutral-700 text-gray-700 dark:text-neutral-200 text-sm">
                  {data.final_result?.summary || data.assistant_response ? (
                    <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
                      {data.final_result?.summary || data.assistant_response || ''}
                    </ReactMarkdown>
                  ) : (
                    '—'
                  )}
                </div>
              </details>

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
    </Sheet>
  );
};

export default ExplorerPanel;

