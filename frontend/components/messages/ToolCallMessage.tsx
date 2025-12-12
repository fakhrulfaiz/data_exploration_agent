'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { markdownComponents } from '../../utils/markdownComponents';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Check, X, Clock } from 'lucide-react';

type ToolCallStatus = 'pending' | 'approved' | 'rejected';

interface ToolCallInput {
  query?: string;
  expression?: string;
  to?: string;
  subject?: string;
  body?: string;
  [key: string]: any;
}

interface ToolCallOutput {
  results?: Array<{ title: string; url: string }>;
  result?: number;
  success?: boolean;
  message?: string;
  [key: string]: any;
}

interface ToolCall {
  id: string;
  name: string;
  input: ToolCallInput;
  status: ToolCallStatus;
  output?: ToolCallOutput | string | null;
  explanation?: string;
}

interface ToolCallMessageProps {
  toolCalls: ToolCall[];
  content?: string;
}

export const ToolCallMessage: React.FC<ToolCallMessageProps> = ({ toolCalls, content }) => {
  // Determine effective status: enabled if has content OR output, disabled if neither
  const getEffectiveStatus = (call: ToolCall): ToolCallStatus | 'disabled' => {
    // Enable if there's content OR if the tool call has output/result
    if ((content && content.trim() !== '') || (call.output && call.output !== null && call.output !== '')) {
      return call.status;
    }
    // Disable if no content and no output yet (still calling)
    return 'disabled';
  };

  const getStatusColor = (status: ToolCallStatus | 'disabled'): string => {
    switch (status) {
      case 'approved':
        return 'text-green-600 dark:text-green-400';
      case 'rejected':
        return 'text-red-600 dark:text-red-400';
      case 'disabled':
        return 'text-muted-foreground opacity-50';
      default:
        return 'text-yellow-600 dark:text-yellow-400';
    }
  };

  const getStatusIcon = (status: ToolCallStatus | 'disabled') => {
    switch (status) {
      case 'approved':
        return <Check className="w-4 h-4" />;
      case 'rejected':
        return <X className="w-4 h-4" />;
      case 'disabled':
        return <Clock className="w-4 h-4 opacity-50" />;
      default:
        return <Clock className="w-4 h-4" />;
    }
  };

  const formatContent = (content: any): string => {
    if (typeof content === 'string') {
      return content;
    }
    return `\`\`\`json\n${JSON.stringify(content, null, 2)}\n\`\`\``;
  };

  return (
    <>
      {content && (
        <div className="mb-3 prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
            {content}
          </ReactMarkdown>
        </div>
      )}

      <Accordion type="single" collapsible className="space-y-2">
        {toolCalls.map((call) => {
          const effectiveStatus = getEffectiveStatus(call);
          const isDisabled = effectiveStatus === 'disabled';

          return (
            <AccordionItem
              key={call.id}
              value={call.id}
              className={`border border-border !border-b rounded-lg px-3 bg-background shadow-sm ${isDisabled ? 'opacity-60 pointer-events-none' : ''}`}
            >
              <AccordionTrigger
                className={`hover:no-underline py-2.5 ${isDisabled ? 'cursor-not-allowed pointer-events-none' : ''}`}
                onClick={(e) => {
                  if (isDisabled) {
                    e.preventDefault();
                    e.stopPropagation();
                  }
                }}
              >
                <div className="flex items-center gap-3 w-full">
                  <div className={`${getStatusColor(effectiveStatus)}`}>
                    {getStatusIcon(effectiveStatus)}
                  </div>
                  <div className="flex-1 text-left">
                    <div className="font-semibold text-foreground">
                      Call: {call.name}
                    </div>
                    <div className="text-sm text-muted-foreground capitalize">
                      {isDisabled ? 'calling...' : effectiveStatus}
                    </div>
                  </div>
                </div>
              </AccordionTrigger>

              <AccordionContent className="pb-2">
                <div className="space-y-3 pt-1.5">
                  <div>
                    <h3 className="font-semibold text-sm text-muted-foreground mb-1.5">
                      Input:
                    </h3>
                    <div className="bg-background border border-border text-foreground p-2 rounded text-sm overflow-x-auto prose prose-sm dark:prose-invert max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {formatContent(call.input)}
                      </ReactMarkdown>
                    </div>
                  </div>

                  {call.output && (
                    <div>
                      <h3 className="font-semibold text-sm text-muted-foreground mb-1.5">
                        Output:
                      </h3>
                      <div className={`p-2 rounded text-sm overflow-x-auto prose prose-sm dark:prose-invert max-w-none ${call.status === 'approved'
                          ? 'bg-accent text-accent-foreground'
                          : call.status === 'rejected'
                            ? 'bg-destructive/15 text-destructive'
                            : 'bg-background border border-border text-foreground'
                        }`}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {formatContent(call.output)}
                        </ReactMarkdown>
                      </div>
                    </div>
                  )}
                </div>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </>
  );
};


