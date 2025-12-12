'use client'

import React from 'react';


export type ExplorerStep = {
  id: number;
  type: string;
  decision?: string;
  reasoning?: string;
  input?: string;
  output?: string;
  confidence?: number;
  why_chosen?: string;
  timestamp?: string;
};

interface StepDetailsProps {
  steps: ExplorerStep[];
  className?: string;
}

const StepDetails: React.FC<StepDetailsProps> = ({ steps, className = '' }) => {
  if (!Array.isArray(steps) || steps.length === 0) {
    return null;
  }

  return (
    <div className={className}>
      <div className="text-base text-gray-800 dark:text-neutral-200 font-medium mb-2">Steps</div>
      <div className="space-y-3">
        {steps.map((s) => (
          <details key={s.id} className="border border-gray-200 dark:border-neutral-700 rounded">
            <summary className="list-none cursor-pointer select-none p-3 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-neutral-800">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-6 h-6 text-xs font-semibold rounded-full bg-gray-200 dark:bg-neutral-700 text-gray-700 dark:text-neutral-200">
                  {s.id}
                </span>
                <span className="font-medium text-gray-800 dark:text-neutral-200 text-base">{s.type}</span>
              </div>
              <div className="flex items-center gap-2">
                {typeof s.confidence === 'number' ? (
                  <span className="text-sm text-green-700 dark:text-green-300 bg-green-100 dark:bg-green-900/30 px-2 py-0.5 rounded">
                    {(s.confidence * 100).toFixed(0)}%
                  </span>
                ) : (
                  <span className="text-sm text-gray-500 dark:text-neutral-400 bg-gray-100 dark:bg-neutral-700 px-2 py-0.5 rounded">
                    No confidence
                  </span>
                )}
                <span className="text-sm text-gray-500 dark:text-neutral-400">
                  {s.timestamp ? new Date(s.timestamp).toLocaleTimeString('en-MY', { timeZone: 'Asia/Kuala_Lumpur' }) : ''}
                </span>
              </div>
            </summary>
            <div className="p-3 border-t border-gray-200 dark:border-neutral-700 space-y-2">
              {s.decision ? (
                <div className="text-base text-gray-700 dark:text-neutral-200">{s.decision}</div>
              ) : (
                <div className="text-base text-gray-500 dark:text-neutral-400 italic">No decision provided</div>
              )}
              {s.reasoning ? (
                <div className="text-sm text-gray-600 dark:text-neutral-300">{s.reasoning}</div>
              ) : (
                <div className="text-sm text-gray-500 dark:text-neutral-400 italic">No reasoning provided</div>
              )}
              {s.input && (
                <div>
                  <div className="text-sm text-gray-500 dark:text-neutral-400 mb-1">Input</div>
                  <pre className="text-sm bg-gray-50 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded p-2 overflow-x-auto whitespace-pre-wrap text-gray-700 dark:text-neutral-200 slim-scroll-x">
                    {s.input}
                  </pre>
                </div>
              )}
              {s.output && (
                <div>
                  <div className="text-sm text-gray-500 dark:text-neutral-400 mb-1">Output</div>
                  <pre className="text-sm bg-gray-50 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded p-2 overflow-x-auto whitespace-pre-wrap text-gray-700 dark:text-neutral-200 slim-scroll-x">
                    {s.output}
                  </pre>
                </div>
              )}
              {s.why_chosen ? (
                <div className="text-sm text-gray-600 dark:text-neutral-300">Why: {s.why_chosen}</div>
              ) : (
                <div className="text-sm text-gray-500 dark:text-neutral-400 italic">No explanation provided</div>
              )}
              {s.timestamp && (
                <div className="text-[11px] text-gray-500 dark:text-neutral-400">
                  {new Date(s.timestamp).toLocaleString('en-MY', { timeZone: 'Asia/Kuala_Lumpur' })}
                </div>
              )}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
};

export default StepDetails;
