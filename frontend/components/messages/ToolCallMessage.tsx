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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Check, X, Clock, AlertCircle, AlertTriangle, CheckCircle2, XCircle, Code, Edit3 } from 'lucide-react';

type ToolCallStatus = 'pending' | 'approved' | 'rejected' | 'error';

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

interface InternalTool {
  name: string;
  status: 'completed' | 'running' | 'error';
}

interface GeneratedContent {
  type: 'sql' | 'code' | 'text';
  content: string;
  editable: boolean;
}

interface ToolCall {
  id: string;
  name: string;
  input: ToolCallInput;
  status: ToolCallStatus;
  output?: ToolCallOutput | string | null;
  explanation?: string;
  // NEW: Support for tools with internal sub-agents
  internalTools?: InternalTool[];
  generatedContent?: GeneratedContent;
}

interface ToolCallMessageProps {
  toolCalls: ToolCall[];
  content?: string;
  // Tool approval props (optional - for hybrid HITL)
  needsApproval?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
  onEdit?: (toolCallId: string, editedContent: string) => void;
  disabled?: boolean;
}

export const ToolCallMessage: React.FC<ToolCallMessageProps> = ({
  toolCalls,
  content,
  needsApproval = false,
  onApprove,
  onReject,
  onEdit,
  disabled = false
}) => {
  // Track edited content for each tool call
  const [editedContent, setEditedContent] = React.useState<Record<string, string>>({});
  const [isEditing, setIsEditing] = React.useState<Record<string, boolean>>({});

  const handleContentEdit = (toolCallId: string, newContent: string) => {
    setEditedContent(prev => ({ ...prev, [toolCallId]: newContent }));
  };

  const toggleEdit = (toolCallId: string) => {
    setIsEditing(prev => ({ ...prev, [toolCallId]: !prev[toolCallId] }));
  };

  const handleApproveWithEdit = () => {
    // If there's edited content, pass it to onEdit callback
    const firstToolCall = toolCalls[0];
    if (firstToolCall && editedContent[firstToolCall.id] && onEdit) {
      onEdit(firstToolCall.id, editedContent[firstToolCall.id]);
    } else if (onApprove) {
      onApprove();
    }
  };

  // Determine effective status: enabled if has content OR output, disabled if neither
  const getEffectiveStatus = (call: ToolCall): ToolCallStatus | 'disabled' => {
    // Check if output contains error
    if (call.output) {
      const outputStr = typeof call.output === 'string' ? call.output : JSON.stringify(call.output);
      if (outputStr.startsWith('Error:')) {
        return 'error';
      }
    }

    // If tool is approved but no output yet, it's executing (show calling...)
    if (call.status === 'approved' && (!call.output || call.output === null || call.output === '')) {
      return 'disabled';
    }

    // If needsApproval is true and status is still pending, show pending status
    if (needsApproval && call.status === 'pending' && (!call.output || call.output === null || call.output === '')) {
      return 'pending';
    }

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
      case 'error':
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
      case 'error':
        return <AlertCircle className="w-4 h-4" />;
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

      {/* Tool approval alert (only shown when needsApproval=true) */}
      {needsApproval && (
        <Alert className="mb-3 border-0 bg-transparent p-0">
          <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          <AlertTitle className="text-amber-900 dark:text-amber-100">Tool Approval Required</AlertTitle>
          <AlertDescription className="text-amber-800 dark:text-amber-200">
            Please review the tool call below and approve or reject execution.
          </AlertDescription>
        </Alert>
      )}

      <Accordion type="single" collapsible className="space-y-2">
        {toolCalls.map((call) => {
          const effectiveStatus = getEffectiveStatus(call);
          const isDisabled = effectiveStatus === 'disabled';

          // Allow clicking when needs approval (even if no output yet)
          const isClickable = needsApproval || !isDisabled;

          return (
            <AccordionItem
              key={call.id}
              value={call.id}
              className={`border border-border !border-b rounded-lg px-3 bg-background shadow-sm ${isDisabled && !needsApproval ? 'opacity-60 pointer-events-none' : ''}`}
            >
              <AccordionTrigger
                className={`hover:no-underline py-2.5 ${!isClickable ? 'cursor-not-allowed pointer-events-none' : ''}`}
                onClick={(e) => {
                  if (!isClickable) {
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
                      {isDisabled ? 'calling...' : (needsApproval && effectiveStatus === 'pending' ? 'awaiting approval' : effectiveStatus)}
                    </div>
                  </div>
                </div>
              </AccordionTrigger>

              <AccordionContent className="pb-2">
                <div className="space-y-3 pt-1.5">
                  <div className="min-w-0 w-full">
                    <h3 className="font-semibold text-sm text-muted-foreground mb-1.5">
                      Input:
                    </h3>
                    <div className="bg-background border border-border text-foreground p-2 rounded text-sm max-h-60 w-full overflow-auto break-words min-w-0">
                      <div className="prose prose-sm dark:prose-invert max-w-none prose-pre:overflow-x-auto">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {formatContent(call.input)}
                        </ReactMarkdown>
                      </div>
                    </div>
                  </div>

                  {/* NEW: Internal Tools Section */}
                  {call.internalTools && call.internalTools.length > 0 && (
                    <div className="min-w-0 w-full">
                      <h3 className="font-semibold text-sm text-muted-foreground mb-1.5">
                        Internal Tools:
                      </h3>
                      <div className="bg-background border border-border rounded p-2 space-y-1">
                        {call.internalTools.map((tool, idx) => (
                          <div key={idx} className="flex items-center gap-2 text-sm">
                            {tool.status === 'completed' && <Check className="w-3 h-3 text-green-500" />}
                            {tool.status === 'running' && <Clock className="w-3 h-3 text-yellow-500 animate-spin" />}
                            {tool.status === 'error' && <AlertCircle className="w-3 h-3 text-red-500" />}
                            <span className="text-foreground">{tool.name}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* NEW: Generated Content Section */}
                  {call.generatedContent && (
                    <div className="min-w-0 w-full">
                      <div className="flex items-center justify-between mb-1.5">
                        <h3 className="font-semibold text-sm text-muted-foreground">
                          Generated {call.generatedContent.type.toUpperCase()}:
                        </h3>
                        {call.generatedContent.editable && needsApproval && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleEdit(call.id)}
                            className="h-6 px-2 text-xs"
                          >
                            <Edit3 className="w-3 h-3 mr-1" />
                            {isEditing[call.id] ? 'Preview' : 'Edit'}
                          </Button>
                        )}
                      </div>

                      {isEditing[call.id] ? (
                        <textarea
                          className="w-full h-32 p-2 font-mono text-sm bg-background border border-input rounded-md focus:ring-2 focus:ring-ring resize-y"
                          defaultValue={call.generatedContent.content}
                          onChange={(e) => handleContentEdit(call.id, e.target.value)}
                          placeholder={`Edit ${call.generatedContent.type}...`}
                        />
                      ) : (
                        <div className="bg-zinc-900 dark:bg-zinc-950 p-3 rounded-md overflow-x-auto">
                          <pre className="m-0 text-sm font-mono text-zinc-50 whitespace-pre-wrap break-all">
                            <code>{editedContent[call.id] || call.generatedContent.content}</code>
                          </pre>
                        </div>
                      )}

                      {editedContent[call.id] && editedContent[call.id] !== call.generatedContent.content && (
                        <div className="mt-2 text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
                          <AlertCircle className="w-3 h-3" />
                          Content has been modified
                        </div>
                      )}
                    </div>
                  )}

                  {call.output && (
                    <div className="min-w-0 w-full">
                      <h3 className="font-semibold text-sm text-muted-foreground mb-1.5">
                        Output:
                      </h3>
                      <div className={`p-2 rounded text-sm max-h-60 w-full overflow-auto break-words min-w-0 ${call.status === 'approved'
                        ? 'bg-accent text-accent-foreground'
                        : call.status === 'rejected'
                          ? 'bg-destructive/15 text-destructive'
                          : call.status === 'error'
                            ? 'bg-red-50 dark:bg-red-950/20 text-red-900 dark:text-red-100 border border-red-300 dark:border-red-700'
                            : 'bg-background border border-border text-foreground'
                        }`}>
                        <div className="prose prose-sm dark:prose-invert max-w-none prose-pre:overflow-x-auto">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {formatContent(call.output)}
                          </ReactMarkdown>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>

      {/* Approval buttons (only shown when needsApproval=true) */}
      {needsApproval && (onApprove || onReject) && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-border">
          {onApprove && (
            <Button
              onClick={handleApproveWithEdit}
              disabled={disabled}
              className="flex-1"
            >
              <CheckCircle2 className="w-4 h-4 mr-2" />
              {Object.keys(editedContent).length > 0 ? 'Approve with Edits' : 'Approve'}
            </Button>
          )}
          {onReject && (
            <Button
              onClick={onReject}
              disabled={disabled}
              variant="outline"
              className="flex-1"
            >
              <XCircle className="w-4 h-4 mr-2" />
              Reject
            </Button>
          )}
        </div>
      )}
    </>
  );
};


