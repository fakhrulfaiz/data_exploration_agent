import React from 'react';
import { MessageComponentProps } from '@/types/chat';
import { MessageRenderer } from './MessageRenderer';

const Message: React.FC<MessageComponentProps> = ({ 
  message,
  onRetry: _onRetry
}) => {
  const handleAction = (action: string, data?: any) => {
    switch (action) {
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
    <div className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
      <div className={`${message.role === 'user' ? 'max-w-[80%] order-2' : 'w-full order-1'}`}>
        {/* Message content */}
        {message.role === 'user' ? (
          <div className="px-4 py-3 rounded-lg bg-primary text-primary-foreground">
            <div className="break-words prose max-w-none">
              <MessageRenderer message={message} onAction={handleAction} />
            </div>
          </div>
        ) : (
          <div className={`px-4 py-3 ${
            message.messageStatus === 'error'
              ? 'bg-destructive/15 text-destructive border border-destructive/30'
              : message.messageStatus === 'timeout'
              ? 'bg-accent text-accent-foreground border border-border'
              : message.messageStatus === 'approved'
              ? 'bg-accent text-accent-foreground border border-border'
              : message.messageStatus === 'rejected'
              ? 'bg-muted text-muted-foreground border border-border'
            : 'bg-background text-foreground'
          }`}>
            <div className="break-words prose max-w-none">
              <MessageRenderer message={message} onAction={handleAction} />
            </div>
          </div>
        )}

        {/* Timestamp and status */}
        <div className={`text-xs text-muted-foreground mt-0.5 mb-2 ${
          message.role === 'user' ? 'text-right' : 'text-left'
        }`}>
          {message.messageStatus === 'approved' && (
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
