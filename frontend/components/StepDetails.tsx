'use client'

import React from 'react';


export type ExplorerStep = {
  id: number;
  type: string;
  decision?: string;
  reasoning?: string;
  input?: string;
  output?: string;
  tool_justification?: string;
  contrastive_explanation?: string;
  data_evidence?: string;
  counterfactual?: string;
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
      <div className="text-sm text-gray-700 dark:text-neutral-300 font-medium mb-2">Steps</div>
      <div className="space-y-2">
        {steps.map((s) => (
          <details key={s.id} className="border border-gray-200 dark:border-neutral-700 rounded bg-gray-50 dark:bg-neutral-800">
            <summary className="list-none cursor-pointer select-none p-3 flex items-center justify-between hover:bg-gray-100 dark:hover:bg-neutral-700">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-gray-500 dark:text-neutral-400">#{s.id}</span>
                <span className="text-sm font-medium text-gray-800 dark:text-neutral-200">{s.type}</span>
              </div>
              <span className="text-xs text-gray-500 dark:text-neutral-400">
                {s.timestamp ? new Date(s.timestamp).toLocaleTimeString('en-MY', { timeZone: 'Asia/Kuala_Lumpur' }) : ''}
              </span>
            </summary>

            <div className="p-3 border-t border-gray-200 dark:border-neutral-700 space-y-3 text-sm text-gray-700 dark:text-neutral-200">

              {/* Decision */}
              {s.decision && (
                <div>
                  <div className="text-xs text-gray-500 dark:text-neutral-400 mb-1">Decision</div>
                  <div className="text-sm text-gray-800 dark:text-neutral-200">
                    {s.decision}
                  </div>
                </div>
              )}

              {/* Input/Output */}
              {s.input && (
                <div>
                  <div className="text-xs text-gray-500 dark:text-neutral-400 mb-1">Input</div>
                  <pre className="text-xs bg-white dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded p-2 overflow-x-auto whitespace-pre-wrap text-gray-700 dark:text-neutral-300 font-mono">
                    {s.input}
                  </pre>
                </div>
              )}

              {s.output && (
                <div>
                  <div className="text-xs text-gray-500 dark:text-neutral-400 mb-1">Output</div>
                  <pre className="text-xs bg-white dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded p-2 overflow-x-auto whitespace-pre-wrap text-gray-700 dark:text-neutral-300 font-mono">
                    {s.output}
                  </pre>
                </div>
              )}

              {/* Reasoning & Explanations */}
              {s.reasoning && (
                <div>
                  <div className="text-xs text-gray-500 dark:text-neutral-400 mb-1">Reasoning</div>
                  <div className="text-xs text-gray-600 dark:text-neutral-400 italic">
                    {s.reasoning}
                  </div>
                </div>
              )}

              {(s.tool_justification || s.contrastive_explanation || s.data_evidence) && (
                <div className="grid grid-cols-1 gap-2 pt-1 text-xs">
                  {s.tool_justification && (
                    <div className="p-2 bg-white dark:bg-neutral-900 rounded border border-gray-200 dark:border-neutral-700">
                      <span className="font-medium text-gray-700 dark:text-neutral-400">Why this tool: </span>
                      <span className="text-gray-600 dark:text-neutral-400">{s.tool_justification}</span>
                    </div>
                  )}
                  {s.contrastive_explanation && (
                    <div className="p-2 bg-white dark:bg-neutral-900 rounded border border-gray-200 dark:border-neutral-700">
                      <span className="font-medium text-gray-700 dark:text-neutral-400">Alternatives: </span>
                      <span className="text-gray-600 dark:text-neutral-400">{s.contrastive_explanation}</span>
                    </div>
                  )}
                  {s.data_evidence && (
                    <div className="p-2 bg-white dark:bg-neutral-900 rounded border border-gray-200 dark:border-neutral-700">
                      <span className="font-medium text-gray-700 dark:text-neutral-400">Evidence: </span>
                      <span className="text-gray-600 dark:text-neutral-400">{s.data_evidence}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Counterfactual - NEW */}
              {s.counterfactual && (
                <div className="p-2 bg-blue-50 dark:bg-blue-900/20 rounded border border-blue-200 dark:border-blue-800">
                  <span className="font-medium text-blue-700 dark:text-blue-400 text-xs">What-if: </span>
                  <span className="text-blue-600 dark:text-blue-300 text-xs italic">{s.counterfactual}</span>
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
