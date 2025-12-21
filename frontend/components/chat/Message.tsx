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
  const hasToolCalls = message.content?.some(block => block.type === 'tool_calls') || false;

  const getMessageStatus = (): 'approved' | 'rejected' | 'error' | 'timeout' | undefined => {
    if (!message.content || message.content.length === 0) return undefined;

    if (message.content.some(block => block.messageStatus === 'error')) {
      return 'error';
    }

    if (message.content.some(block => block.messageStatus === 'timeout')) {
      return 'timeout';
    }

    const blocksWithStatus = message.content.filter(block => block.messageStatus);
    if (blocksWithStatus.length > 0 && blocksWithStatus.every(block => block.messageStatus === 'approved')) {
      return 'approved';
    }

    if (message.content.some(block => block.messageStatus === 'rejected')) {
      return 'rejected';
    }

    return undefined;
  };

  const messageStatus = getMessageStatus();

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


  const hasContent = message.content && message.content.length > 0;

  if (!hasContent) {
    return null;
  }
  return (
    <div className={`flex mb-2 ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
      {message.sender === 'assistant' && (
        <div className="flex-shrink-0 mr-2 mt-1">
          {showIcon ? (
            <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center">
              <Bot className="w-5 h-5 text-white" />
            </div>
          ) : (
            <div className="w-8 h-8" />
          )}
        </div>
      )}

      <div className={`${message.sender === 'user' ? 'max-w-[80%] order-2' : 'flex-1 min-w-0 overflow-hidden order-1'}`}>
        {message.sender === 'user' ? (
          <div className="px-4 py-3 rounded-lg bg-primary text-primary-foreground">
            <div className="break-words">
              <MessageRenderer message={message} onAction={handleAction} />
            </div>
          </div>
        ) : (
          <div className={`px-4 py-3 ${messageStatus === 'error'
            ? 'rounded-lg border border-destructive/50 text-foreground'
            : messageStatus === 'timeout'
              ? 'rounded-lg border border-orange-500/50 text-foreground'
              : messageStatus === 'approved' && !hasToolCalls
                ? 'rounded-lg border border-green-500/50 text-foreground'
                : messageStatus === 'rejected'
                  ? 'rounded-lg border border-red-500/50 text-foreground'
                  : 'bg-background text-foreground'
            }`}>
            <div className="break-words">
              <MessageRenderer message={message} onAction={handleAction} />
            </div>
          </div>
        )}

        <div className={`text-xs text-muted-foreground mt-0.5 mb-2 ${message.sender === 'user' ? 'text-right' : 'text-left'
          }`}>
          {messageStatus === 'approved' && !hasToolCalls && (
            <span className="ml-2 text-green-600 font-medium">✓ Approved</span>
          )}
          {messageStatus === 'rejected' && (
            <span className="ml-2 text-red-600 font-medium">Cancelled</span>
          )}
          {messageStatus === 'timeout' && (
            <span className="ml-2 text-orange-600 font-medium">Timed out</span>
          )}
          {messageStatus === 'error' && (
            <span className="ml-2 text-red-600 font-medium">Error</span>
          )}
        </div>
      </div>
    </div>
  );
};

export default Message;
