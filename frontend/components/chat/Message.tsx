import React from 'react';
import { MessageComponentProps } from '@/types/chat';
import { MessageRenderer } from './MessageRenderer';
import { Bot } from 'lucide-react';

const Message: React.FC<MessageComponentProps> = ({
  message,
  onRetry: _onRetry,
  showIcon = true, // Default to true for backward compatibility
  onApproveBlock,
  onRejectBlock
}) => {
  // Check if message contains tool calls
  const hasToolCalls = message.content?.some(block => block.type === 'tool_calls') || false;
  const handleAction = (action: string, data?: any) => {
    switch (action) {
      case 'approveToolCall':
      case 'approvePlan':
        if (onApproveBlock && data?.id) {
          onApproveBlock(data.id);
        }
        break;
      case 'rejectToolCall':
      case 'rejectPlan':
        if (onRejectBlock && data?.id) {
          onRejectBlock(data.id);
        }
        break;
      case 'openExplorer':
        if ((window as any).openExplorer) {
          (window as any).openExplorer(data);
        }
        break;
      case 'openVisualization':
        if ((window as any).openVisualization) {
          (window as any).openVisualization(data);
        }
        break;
    }
  };


  // Check if message has content (always an array of content blocks)
  const hasContent = message.content && message.content.length > 0;

  if (!hasContent) {
    return null;
  }
  // Regular message layout
  return (
    <div className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
      {/* Assistant icon - always reserve space for alignment */}
      {message.sender === 'assistant' && (
        <div className="flex-shrink-0 mr-2 mt-1">
          {showIcon ? (
            <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center">
              <Bot className="w-5 h-5 text-white" />
            </div>
          ) : (
            // Empty space to maintain alignment
            <div className="w-8 h-8" />
          )}
        </div>
      )}

      <div className={`${message.sender === 'user' ? 'max-w-[80%] order-2' : 'flex-1 min-w-0 overflow-hidden order-1'}`}>
        {/* Message content */}
        {message.sender === 'user' ? (
          <div className="px-4 py-3 rounded-lg bg-primary text-primary-foreground">
            <div className="break-words">
              <MessageRenderer message={message} onAction={handleAction} />
            </div>
          </div>
        ) : (
          <div className={`px-4 py-3 ${message.messageStatus === 'error'
            ? 'bg-destructive/15 text-destructive border border-destructive/30'
            : message.messageStatus === 'timeout'
              ? 'bg-accent text-accent-foreground border border-border'
              : message.messageStatus === 'approved' && !hasToolCalls
                ? 'bg-accent text-accent-foreground border border-border'
                : message.messageStatus === 'rejected'
                  ? 'bg-muted text-muted-foreground border border-border'
                  : 'bg-background text-foreground'
            }`}>
            <div className="break-words">
              <MessageRenderer message={message} onAction={handleAction} />
            </div>
          </div>
        )}

        {/* Timestamp and status */}
        <div className={`text-xs text-muted-foreground mt-0.5 mb-2 ${message.sender === 'user' ? 'text-right' : 'text-left'
          }`}>
          {message.messageStatus === 'approved' && !hasToolCalls && (
            <span className="ml-2 text-green-600 font-medium">✓ Approved</span>
          )}
          {message.messageStatus === 'rejected' && (
            <span className="ml-2 text-red-600 font-medium">Cancelled</span>
          )}
          {message.messageStatus === 'timeout' && (
            <span className="ml-2 text-orange-600 font-medium">Timed out</span>
          )}
          {message.messageStatus === 'error' && (
            <span className="ml-2 text-red-600 font-medium">Error</span>
          )}
        </div>
      </div>
    </div>
  );
};

export default Message;
