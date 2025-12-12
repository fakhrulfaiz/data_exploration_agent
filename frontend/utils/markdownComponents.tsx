'use client';

import { Copy } from 'lucide-react';
import { Components } from 'react-markdown';

export const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0 text-inherit">{children}</p>,
  ol: ({ children }) => <ol className="list-decimal list-outside mb-2 space-y-1 pl-6">{children}</ol>,
  ul: ({ children }) => <ul className="list-disc list-outside mb-2 space-y-1 pl-6">{children}</ul>,
  li: ({ children }) => <li className="text-inherit">{children}</li>,
  // Render inline code and fenced code blocks differently
  code: ({ node, inline, className, children, ...props }: any) => {
    if (inline) {
      return (
        <code className="bg-gray-200 dark:bg-neutral-700 dark:text-neutral-200 px-1 rounded text-sm font-mono">
          {children}
        </code>
      );
    }

    const rawCode = String(children || '').replace(/\n$/, '');
    const languageClass = className || '';

    // Heuristic: if code block is single-line and short, render as inline instead of block
    const isSingleLine = !rawCode.includes('\n');
    if (isSingleLine && rawCode.length <= 120) {
      return (
        <code className="bg-gray-200 dark:bg-neutral-700 dark:text-neutral-200 px-1 rounded text-sm font-mono">
          {rawCode}
        </code>
      );
    }

    const handleCopy = () => {
      try {
        if (typeof navigator !== 'undefined') {
          void navigator.clipboard.writeText(rawCode);
        }
      } catch {
        // ignore
      }
    };

    return (
      <div className="relative my-3">
        <button
          onClick={handleCopy}
          className="absolute right-2 top-2 text-xs bg-slate-700 dark:bg-neutral-700 hover:bg-slate-600 dark:hover:bg-neutral-600 text-slate-100 dark:text-neutral-100 px-2 py-1 rounded border border-slate-500 dark:border-neutral-600"
          type="button"
        >
          <Copy className="w-4 h-4" />
        </button>
        <pre className="bg-slate-800 dark:bg-neutral-900 text-slate-50 dark:text-neutral-100 p-4 rounded-lg overflow-x-auto slim-scroll-x text-sm border border-slate-700 dark:border-neutral-700 shadow-sm">
          <code className={`${languageClass} font-mono whitespace-pre`}>{rawCode}</code>
        </pre>
      </div>
    );
  },
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 underline"
    >
      {children}
    </a>
  ),
  img: ({ src, alt, title }) => (
    <img
      src={src}
      alt={alt || ''}
      title={title}
      className="w-full max-w-full h-auto md:max-w-[500px] lg:max-w-[600px] sm:max-w-[400px] rounded-lg shadow-sm my-4 cursor-pointer hover:opacity-80 transition-opacity"
      onClick={() => {
        if (typeof window !== 'undefined' && typeof src === 'string') {
          window.open(src, '_blank');
        }
      }}
    />
  ),
  // Table components for markdown tables
  table: ({ children }) => (
    <div className="overflow-x-auto my-4">
      <table className="min-w-full border border-gray-300 dark:border-neutral-700 rounded-lg overflow-hidden">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gray-50 dark:bg-neutral-900">
      {children}
    </thead>
  ),
  tbody: ({ children }) => (
    <tbody className="bg-white dark:bg-neutral-900 divide-y divide-gray-200 dark:divide-neutral-800">
      {children}
    </tbody>
  ),
  tr: ({ children }) => (
    <tr className="hover:bg-gray-50 dark:hover:bg-neutral-700">
      {children}
    </tr>
  ),
  th: ({ children }) => (
    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider border-b border-gray-300 dark:border-neutral-700">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-4 py-3 text-sm text-gray-900 dark:text-neutral-200 border-b border-gray-200 dark:border-neutral-800">
      {children}
    </td>
  )
};