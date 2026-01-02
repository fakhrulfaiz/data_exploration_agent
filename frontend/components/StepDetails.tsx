'use client'

import React, { useState } from 'react';
import { StepExplanation, ToolCall } from '@/types/chat';
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ChevronDown, ChevronRight } from 'lucide-react';

interface StepDetailsProps {
  steps: StepExplanation[];
  className?: string;
}

const ToolCallDisplay: React.FC<{ toolCall: ToolCall; index: number }> = ({ toolCall, index }) => {
  return (
    <div className="border border-gray-200 dark:border-neutral-700 rounded p-2 bg-white dark:bg-neutral-900">
      <div className="text-xs font-medium text-gray-600 dark:text-neutral-400 mb-2">
        Call {index + 1}: {toolCall.tool_name}
      </div>

      {/* Input */}
      {toolCall.input && (
        <div className="mb-2">
          <div className="text-xs text-gray-500 dark:text-neutral-400 mb-1">Input</div>
          <pre className="text-xs bg-gray-50 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded p-2 overflow-x-auto whitespace-pre-wrap text-gray-700 dark:text-neutral-300 font-mono">
            {toolCall.input}
          </pre>
        </div>
      )}

      {/* Output */}
      {toolCall.output && (
        <div>
          <div className="text-xs text-gray-500 dark:text-neutral-400 mb-1">Output</div>
          <pre className="text-xs bg-gray-50 dark:bg-neutral-800 border border-gray-200 dark:border-neutral-700 rounded p-2 overflow-x-auto whitespace-pre-wrap text-gray-700 dark:text-neutral-300 font-mono">
            {toolCall.output}
          </pre>
        </div>
      )}
    </div>
  );
};

const StepItem: React.FC<{ step: StepExplanation }> = ({ step }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="border border-gray-200 dark:border-neutral-700 rounded bg-gray-50 dark:bg-neutral-800">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full text-left p-3 flex items-center justify-between hover:bg-gray-100 dark:hover:bg-neutral-700 transition-colors rounded-t (isOpen ? '' : 'rounded-b')"
      >
        <div className="flex items-center gap-2">
          {isOpen ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
          <span className="text-xs font-medium text-gray-500 dark:text-neutral-400">#{step.id}</span>
          <span className="text-sm font-medium text-gray-800 dark:text-neutral-200">
            {step.tool_calls[0]?.tool_name || 'Unknown Tool'}
            {step.tool_calls.length > 1 && ` (${step.tool_calls.length} calls)`}
          </span>
        </div>
        <span className="text-xs text-gray-500 dark:text-neutral-400">
          {step.timestamp ? new Date(step.timestamp).toLocaleTimeString('en-MY', { timeZone: 'Asia/Kuala_Lumpur' }) : ''}
        </span>
      </button>

      {isOpen && (
        <div className="p-3 border-t border-gray-200 dark:border-neutral-700 space-y-3 text-sm text-gray-700 dark:text-neutral-200 animate-in slide-in-from-top-2 duration-200">
          {/* Decision */}
          {step.decision && (
            <div>
              <div className="text-xs text-gray-500 dark:text-neutral-400 mb-1">Decision</div>
              <div className="text-sm text-gray-800 dark:text-neutral-200">
                {step.decision}
              </div>
            </div>
          )}

          {/* Reasoning */}
          {step.reasoning && (
            <div>
              <div className="text-xs text-gray-500 dark:text-neutral-400 mb-1">Reasoning</div>
              <div className="text-xs text-gray-600 dark:text-neutral-400 italic">
                {step.reasoning}
              </div>
            </div>
          )}

          {/* Tool Calls */}
          <div className="space-y-2">
            <div className="text-xs text-gray-500 dark:text-neutral-400">Tool Calls ({step.tool_calls.length})</div>

            {step.tool_calls.length > 1 ? (
              <Tabs defaultValue={step.tool_calls[0]?.tool_call_id} className="w-full">
                <TabsList className="w-full justify-start h-auto flex-wrap gap-1 bg-transparent p-0 mb-2">
                  {step.tool_calls.map((tc, idx) => (
                    <TabsTrigger
                      key={tc.tool_call_id}
                      value={tc.tool_call_id}
                      className="data-[state=active]:bg-white dark:data-[state=active]:bg-neutral-900 border border-transparent data-[state=active]:border-gray-200 dark:data-[state=active]:border-neutral-700"
                    >
                      Call {idx + 1}: {tc.tool_name}
                    </TabsTrigger>
                  ))}
                </TabsList>
                {step.tool_calls.map((tc, idx) => (
                  <TabsContent key={tc.tool_call_id} value={tc.tool_call_id} className="mt-0">
                    <ToolCallDisplay toolCall={tc} index={idx} />
                  </TabsContent>
                ))}
              </Tabs>
            ) : (
              step.tool_calls.map((tc, idx) => (
                <ToolCallDisplay key={tc.tool_call_id} toolCall={tc} index={idx} />
              ))
            )}
          </div>

          {/* Explanations (Step Level) */}
          {(step.tool_justification || step.data_evidence || step.counterfactual) && (
            <div className="grid grid-cols-1 gap-2 pt-1 text-xs">
              {step.tool_justification && (
                <div className="p-2 bg-white dark:bg-neutral-900 rounded border border-gray-200 dark:border-neutral-700">
                  <span className="font-medium text-gray-700 dark:text-neutral-400">Why this tool: </span>
                  <span className="text-gray-600 dark:text-neutral-400">{step.tool_justification}</span>
                </div>
              )}
              {step.data_evidence && (
                <div className="p-2 bg-white dark:bg-neutral-900 rounded border border-gray-200 dark:border-neutral-700">
                  <span className="font-medium text-gray-700 dark:text-neutral-400">Evidence: </span>
                  <span className="text-gray-600 dark:text-neutral-400">{step.data_evidence}</span>
                </div>
              )}
              {step.counterfactual && (
                <div className="p-2 bg-blue-50 dark:bg-blue-900/20 rounded border border-blue-200 dark:border-blue-800">
                  <span className="font-medium text-blue-700 dark:text-blue-400 text-xs">What-if: </span>
                  <span className="text-blue-600 dark:text-blue-300 text-xs italic">{step.counterfactual}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const StepDetails: React.FC<StepDetailsProps> = ({ steps, className = '' }) => {
  if (!Array.isArray(steps) || steps.length === 0) {
    return null;
  }

  return (
    <div className={className}>
      <div className="text-sm text-gray-700 dark:text-neutral-300 font-medium mb-2">Steps ({steps.length})</div>
      <div className="space-y-2">
        {steps.map((step) => (
          <StepItem key={step.id} step={step} />
        ))}
      </div>
    </div>
  );
};

export default StepDetails;
