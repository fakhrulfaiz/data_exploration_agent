'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { markdownComponents } from '../../utils/markdownComponents';
import { ToolErrorInterrupt } from '@/types/chat';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Check, X, Clock, AlertCircle, AlertTriangle, CheckCircle2, XCircle, Code, Edit3, RotateCw } from 'lucide-react';

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
  // Error interrupt props
  errorInterrupt?: ToolErrorInterrupt;
  onRetry?: () => void;
  onReplan?: () => void;
  onCancel?: () => void;
}

// Helper to parse error from tool output
function parseToolError(output: any): ToolErrorInterrupt | null {
  if (!output) return null;

  try {
    // Parse output if it's a string
    const parsed = typeof output === 'string' ? JSON.parse(output) : output;

    // Check if output contains error
    if (parsed.error && parsed.error_type) {
      return {
        type: 'tool_error',
        message: parsed.error,
        error_details: [{
          tool_name: parsed.tool_name || 'unknown',
          tool_call_id: '',
          error_message: parsed.error,
          error_type: parsed.error_type,
          details: parsed.details || {},
          recoverable: parsed.recoverable !== false,
          full_output: typeof output === 'string' ? output : JSON.stringify(output),
          detection_method: 'output_parsing'
        }],
        current_step_index: 0,
        options: parsed.recoverable !== false ? ['retry', 'replan', 'cancel'] : ['replan', 'cancel']
      };
    }
  } catch (e) {
    // Not JSON or doesn't match error format
  }

  return null;
}

// Helper component for animated pending state with timeouts
const PendingIndicator = ({ toolName }: { toolName: string }) => {
  const [elapsed, setElapsed] = React.useState(0);
  
  React.useEffect(() => {
    const timer = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  let statusText = 'calling...';
  // Context-aware status messages for long-running tools
  if (elapsed > 3) {
     if (toolName.includes('image') || toolName.includes('batch')) {
        statusText = 'processing images, please be patient...';
     } else if (elapsed > 10) {
        statusText = 'still working...';
     }
  }

  return (
    <span className="flex items-center gap-2 text-amber-600 dark:text-amber-500 font-medium">
       <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
        </span>
       <span className="animate-pulse">{statusText}</span>
       <span className="text-xs opacity-70 font-mono">({elapsed}s)</span>
    </span>
  );
};

export const ToolCallMessage: React.FC<ToolCallMessageProps> = ({
  toolCalls,
  content,
  needsApproval = false,
  onApprove,
  onReject,
  onEdit,
  disabled = false,
  errorInterrupt,
  onRetry,
  onReplan,
  onCancel
}) => {
  // Track edited content for each tool call
  const [editedContent, setEditedContent] = React.useState<Record<string, string>>({});
  const [editingToolId, setEditingToolId] = React.useState<string | null>(null);
  const [isEditing, setIsEditing] = React.useState<Record<string, boolean>>({});

  // Auto-detect errors from tool output
  const detectedError = React.useMemo(() => {
    if (errorInterrupt) return errorInterrupt; // Use explicit error if provided

    // Check each tool call for errors in output
    for (const toolCall of toolCalls) {
      const error = parseToolError(toolCall.output);
      if (error) {
        return error;
      }
    }
    return null;
  }, [toolCalls, errorInterrupt]);

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
    // Check if output contains error (using the helper)
    if (call.output) {
      const error = parseToolError(call.output);
      if (error) {
        return 'error';
      }

      const outputStr = typeof call.output === 'string' ? call.output : JSON.stringify(call.output);
      if (outputStr.startsWith('Error:')) {
        return 'error';
      }
    }

    // If tool is approved but no output yet, it's executing (show calling...)
    // Also include 'pending' if no approval is needed (auto-execution)
    if ((call.status === 'approved' || (!needsApproval && call.status === 'pending')) && (!call.output || call.output === null || call.output === '')) {
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
        return 'text-amber-500 dark:text-amber-400'; // Changed to amber for pending
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
        return <RotateCw className="w-4 h-4 animate-spin" />; // Changed to spinner
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



      {/* Alert message - different for errors vs normal approval */}
      {needsApproval && detectedError && (
        <Alert className="mb-3 border-0 bg-transparent p-0">
          <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
          <AlertTitle className="text-red-900 dark:text-red-100">Tool Execution Error</AlertTitle>
          <AlertDescription className="text-red-800 dark:text-red-200">
            The tool encountered an error. Please choose how to proceed.
          </AlertDescription>
        </Alert>
      )}

      {needsApproval && !detectedError && (
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
          // Check if this specific call has an error
          const parsedCallError = parseToolError(call.output);

          // Allow clicking when needs approval (even if no output yet)
          const isClickable = needsApproval || !isDisabled;

          return (
            <AccordionItem
              key={call.id}
              value={call.id}
              className={`border border-border !border-b rounded-lg px-3 bg-background shadow-sm ${isDisabled && !needsApproval ? 'opacity-90' : ''}`}
            >
              <AccordionTrigger
                className={`hover:no-underline py-2.5`}
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
                      {isDisabled ? (
                        <PendingIndicator toolName={call.name} />
                      ) : (
                        needsApproval && effectiveStatus === 'pending' ? 'awaiting approval' : effectiveStatus
                      )}
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
                      <h3 className="font-semibold text-sm text-muted-foreground mb-1.5 ">
                        {parsedCallError ? 'Error Details:' : 'Output:'}
                      </h3>

                      {parsedCallError ? (
                        // Render Formatted Error Inside Output Section
                        <div className="p-3 rounded-md bg-destructive/5 border border-destructive/20 text-sm space-y-3">
                          <div className="flex items-center gap-2 text-destructive font-medium">
                            <AlertCircle className="w-4 h-4" />
                            <span>Execution Failed</span>
                            {parsedCallError.error_details[0]?.recoverable && (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 ml-auto border border-green-200 dark:border-green-800">
                                Recoverable
                              </span>
                            )}
                          </div>

                          {parsedCallError.error_details.map((error, idx) => (
                            <div key={idx} className="space-y-2">
                              <p className="text-destructive/90 font-mono text-xs break-words bg-destructive/5 p-2 rounded">
                                {error.error_message}
                              </p>

                              {/* Generic Details Rendering - Simple Text Only */}
                              {error.details && Object.entries(error.details).map(([key, value]) => {
                                if (!value) return null;

                                // Format label from key (e.g., 'sql_query' -> 'SQL Query')
                                const label = key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

                                return (
                                  <div key={key} className="text-xs text-muted-foreground break-words">
                                    <span className="font-semibold text-foreground/80">{label}:</span>{' '}
                                    <span className="font-mono text-foreground/70">{String(value)}</span>
                                  </div>
                                );
                              })}
                            </div>
                          ))}
                        </div>
                      ) : (
                        // Render Regular Output
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
                      )}
                    </div>
                  )}
                </div>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>

      {/* Approval buttons (shown when needsApproval=true and NO error detected) */}
      {needsApproval && !detectedError && (onApprove || onReject) && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-border">
          {onApprove && (
            <Button
              onClick={handleApproveWithEdit}
              disabled={disabled}
              className="flex-1"
            >
              <CheckCircle2 className="w-4 h-4 mr-2" />
              Approve
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

      {/* Error recovery buttons (shown when needsApproval=true AND error detected) */}
      {needsApproval && detectedError && (onRetry || onReplan || onCancel) && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-border">
          {detectedError.error_details[0]?.recoverable && onRetry && (
            <Button
              onClick={onRetry}
              disabled={disabled}
              className="flex-1"
            >
              <RotateCw className="w-4 h-4 mr-2" />
              Retry
            </Button>
          )}
          {onReplan && (
            <Button
              onClick={onReplan}
              disabled={disabled}
              variant="outline"
              className="flex-1"
            >
              <Code className="w-4 h-4 mr-2" />
              Replan
            </Button>
          )}
          {onCancel && (
            <Button
              onClick={onCancel}
              disabled={disabled}
              variant="destructive"
              className="flex-1"
            >
              <XCircle className="w-4 h-4 mr-2" />
              Cancel
            </Button>
          )}
        </div>
      )}
    </>
  );
};
