import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message, ContentBlock, isTextBlock, isToolCallsBlock, isExplorerBlock, isVisualizationsBlock, isPlanBlock, isErrorBlock, isExplanationBlock, isReasoningChainBlock } from '@/types/chat';
import { ExplorerMessage } from '@/components/messages/ExplorerMessage';
import { markdownComponents } from '@/utils/markdownComponents';
import VisualizationMessage from '@/components/messages/VisualizationMessage';
import { ToolCallMessage } from '@/components/messages/ToolCallMessage';
import { PlanMessage } from '@/components/messages/PlanMessage';
import { ErrorMessage } from '@/components/messages/ErrorMessage';
import { ExplanationMessage } from '@/components/messages/ExplanationMessage';
import { ReasoningChainMessage } from '@/components/messages/ReasoningChainMessage';
import { SqlApprovalMessage } from '@/components/messages/SqlApprovalMessage';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface MessageRendererProps {
  message: Message;
  onAction?: (action: string, data?: any) => void;
}

interface ToolHistoryCollapsibleProps {
  blocks: ContentBlock[];
  collapseUntilIndex: number;
  renderContentBlock: (block: ContentBlock) => React.ReactNode;
}

const ToolHistoryCollapsible: React.FC<ToolHistoryCollapsibleProps> = ({
  blocks,
  collapseUntilIndex,
  renderContentBlock
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // Collect tool names from collapsed portion
  const collapsedBlocks = blocks.slice(0, collapseUntilIndex);
  const remainingBlocks = blocks.slice(collapseUntilIndex);
  const toolNames: string[] = [];
  collapsedBlocks.forEach((block) => {
    if (isToolCallsBlock(block)) {
      block.data.toolCalls.forEach((tc: any) => {
        toolNames.push(tc.name);
      });
    }
  });

  return (
    <div className="content-blocks">
      {/* Collapsible wrapper for history before the latest tool call */}
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <CollapsibleTrigger asChild>
          <button
            className="mb-2 flex items-center gap-2 hover:opacity-80 transition-opacity"
            type="button"
          >
            {isExpanded ? (
              <ChevronDown className="w-4 h-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            )}
            <span className="font-semibold text-foreground">
              Previous steps
            </span>
            {!isExpanded && (
              <span className="text-sm text-muted-foreground">
                ({toolNames.length} {toolNames.length === 1 ? 'tool' : 'tools'})
              </span>
            )}
          </button>
        </CollapsibleTrigger>

        <CollapsibleContent className="data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 duration-200">
          <div className="pt-2">
            {collapsedBlocks.map((block) => renderContentBlock(block))}
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Latest tool call and everything after */}
      {remainingBlocks.map((block) => renderContentBlock(block))}
    </div>
  );
};

const ThoughtCollapsible: React.FC<{ content: string }> = ({ content }) => {
  const [isExpanded, setIsExpanded] = useState(true); // Changed to true - visible by default

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="border border-muted rounded-md bg-muted/30">
      <CollapsibleTrigger asChild>
        <button
          className="flex items-center gap-2 p-2 w-full hover:bg-muted/50 transition-colors rounded-t-md text-left"
          type="button"
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted-foreground" />
          )}
          <span className="font-semibold text-sm text-foreground">
            Thought Process
          </span>
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent className="data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 duration-200">
        <div className="p-3 pt-0 text-sm text-muted-foreground">
          <ReactMarkdown
            components={markdownComponents}
            remarkPlugins={[remarkGfm]}
          >
            {content}
          </ReactMarkdown>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
};

export const MessageRenderer: React.FC<MessageRendererProps> = ({ message, onAction }) => {
  // Helper function to get border styling based on block status
  const getBlockBorderClass = (block: ContentBlock): string => {
    if (!block.messageStatus) return '';

    switch (block.messageStatus) {
      case 'approved':
        return 'border border-green-500/50 rounded-lg p-3';
      case 'rejected':
        return 'border border-red-500/50 rounded-lg p-3';
      case 'error':
        return 'border border-destructive/50 rounded-lg p-3';
      case 'timeout':
        return 'border border-orange-500/50 rounded-lg p-3';
      default:
        return '';
    }
  };

  // Helper function to get status text based on block status
  const getBlockStatusText = (block: ContentBlock): React.ReactNode => {
    if (!block.messageStatus) return null;

    switch (block.messageStatus) {
      case 'approved':
        return <span className="text-xs text-green-600 font-medium ml-2">✓ Approved</span>;
      case 'rejected':
        return <span className="text-xs text-red-600 font-medium ml-2">Cancelled</span>;
      case 'error':
        return <span className="text-xs text-red-600 font-medium ml-2">Error</span>;
      case 'timeout':
        return <span className="text-xs text-orange-600 font-medium ml-2">Timed out</span>;
      default:
        return null;
    }
  };

  const renderContentBlock = (block: ContentBlock) => {
    if (isTextBlock(block)) {
      // Check for SQL approval metadata
      if (block.metadata?.type === 'sql_approval' && block.metadata?.sql) {
        return (
          <div key={block.id} className="content-block sql-approval-block mb-4">
            <SqlApprovalMessage
              data={{
                sql: block.metadata.sql,
                type: 'sql_approval',
                tool_call_id: block.metadata.tool_call_id
              }}
              onApprove={onAction ? () => onAction('approveSql', block) : undefined}
              onReject={onAction ? () => onAction('rejectSql', block) : undefined}
              onEdit={onAction ? (newSql) => onAction('editSql', { ...block, metadata: { ...block.metadata, sql: newSql } }) : undefined}
            />
          </div>
        );
      }

      // Check for Thought blocks
      if (typeof block.data.text === 'string' && block.data.text.includes('Thought: ')) {
        const parts = block.data.text.split(/(Thought:\s[\s\S]*?(?=\n\n|$))/g);

        return (
          <div key={block.id} className="content-block text-block mb-4 last:mb-0">
            {parts.map((part, index) => {
              if (part.startsWith('Thought: ')) {
                // Render thought block
                const thoughtContent = part.replace(/^Thought:\s/, '');
                return (
                  <div key={index} className="mb-4">
                    <ThoughtCollapsible content={thoughtContent} />
                  </div>
                );
              } else if (part.trim()) {
                // Render regular markdown
                return (
                  <div key={index} className="mb-4 last:mb-0">
                    <ReactMarkdown
                      components={markdownComponents}
                      remarkPlugins={[remarkGfm]}
                    >
                      {part}
                    </ReactMarkdown>
                  </div>
                );
              }
              return null;
            })}
          </div>
        );
      }

      return (
        <div key={block.id} className="content-block text-block mb-4 last:mb-0">
          <ReactMarkdown
            components={markdownComponents}
            remarkPlugins={[remarkGfm]}
          >
            {block.data.text}
          </ReactMarkdown>
        </div>
      );
    }

    if (isToolCallsBlock(block)) {
      const mappedToolCalls = block.data.toolCalls.map(toolCall => ({
        id: toolCall.name,
        name: toolCall.name,
        input: toolCall.input,
        output: toolCall.output,
        status: toolCall.status,
        internalTools: toolCall.internalTools,
        generatedContent: toolCall.generatedContent
      }));

      return (
        <div key={block.id} className="content-block tool-calls-block mb-4">
          <ToolCallMessage
            toolCalls={mappedToolCalls}
            content={block.data.content}
            needsApproval={block.needsApproval}
            onApprove={onAction ? () => onAction('approveToolCall', block) : undefined}
            onReject={onAction ? () => onAction('rejectToolCall', block) : undefined}
            onEdit={onAction ? (toolCallId, editedContent) => onAction('editToolCall', { block, toolCallId, editedContent }) : undefined}
          />
        </div>
      );
    }

    if (isExplorerBlock(block)) {
      return (
        <div key={block.id} className="content-block explorer-block mb-4">
          <ExplorerMessage
            checkpointId={block.data.checkpointId}
            data={block.data.explorerData}
            onOpenExplorer={() => onAction?.('openExplorer', { checkpointId: block.data.checkpointId, data: block.data.explorerData })}
          />
        </div>
      );
    }

    if (isVisualizationsBlock(block)) {
      return (
        <div key={block.id} className="content-block visualizations-block mb-4">
          <VisualizationMessage
            checkpointId={block.data.checkpointId}
            charts={block.data.visualizations}
            onOpenVisualization={() => onAction?.('openVisualization', { checkpointId: block.data.checkpointId, charts: block.data.visualizations })}
          />
        </div>
      );
    }

    if (isPlanBlock(block)) {
      const borderClass = getBlockBorderClass(block);
      const statusText = getBlockStatusText(block);

      return (
        <div key={block.id} className={`content-block plan-block mb-4 ${borderClass}`}>
          <PlanMessage
            plan={block.data.plan}
            needsApproval={block.needsApproval}
            onApprove={onAction ? () => onAction('approvePlan', block) : undefined}
            onReject={onAction ? () => onAction('rejectPlan', block) : undefined}
          />
          {statusText && <div className="mt-1">{statusText}</div>}
        </div>
      );
    }

    if (isErrorBlock(block)) {
      return (
        <div key={block.id} className="content-block error-block mb-4">
          <ErrorMessage errorExplanation={block.data} />
        </div>
      );
    }

    if (isExplanationBlock(block)) {
      return (
        <div key={block.id} className="content-block explanation-block mb-4">
          <ExplanationMessage data={block.data} />
        </div>
      );
    }

    if (isReasoningChainBlock(block)) {
      return (
        <div key={block.id} className="content-block reasoning-chain-block mb-4">
          <ReasoningChainMessage data={block.data} />
        </div>
      );
    }
    return null;
  };

  const renderContent = () => {
    // Content is always an array of content blocks
    const contentBlocks = message.content || [];

    // Handle empty content
    if (!contentBlocks || contentBlocks.length === 0) {
      return null;
    }

    // Filter out tool_explanation text blocks if tool_calls block already has the content
    // This prevents duplication while still allowing real-time streaming
    const toolCallsBlock = contentBlocks.find((b: ContentBlock) => b.type === 'tool_calls');
    const toolCallsContent = toolCallsBlock ? (toolCallsBlock.data as any).content : null;

    // Filter: hide text blocks that appear before tool_calls block and match tool_calls content
    // This hides tool_explanation text while keeping the final response text
    const filteredBlocks = toolCallsContent
      ? contentBlocks.filter((block, index) => {
        if (block.type === 'text') {
          const textContent = (block.data as any).text || '';
          const toolCallsIndex = contentBlocks.findIndex((b: ContentBlock) => b.type === 'tool_calls');

          // Hide text block if:
          // 1. It appears before tool_calls block
          // 2. Its content matches or is contained in tool_calls block content
          if (index < toolCallsIndex && toolCallsContent && typeof textContent === 'string' && textContent.trim()) {
            const normalizedText = textContent.trim();
            const normalizedToolContent = toolCallsContent.trim();
            // Check if text content matches tool_calls content (tool explanation)
            if (normalizedToolContent.includes(normalizedText) || normalizedText === normalizedToolContent) {
              return false; // Hide this text block (it's the tool explanation)
            }
          }
        }
        return true;
      })
      : contentBlocks;


    const latestToolCallIndex = filteredBlocks.reduce((acc, block, index) => (
      isToolCallsBlock(block) ? index : acc
    ), -1);


    const hasToolCallHistory = latestToolCallIndex > 0 &&
      filteredBlocks.slice(0, latestToolCallIndex).some(b => isToolCallsBlock(b));

    if (hasToolCallHistory) {
      // Keep blocks in stream order, but collapse older tool calls
      // Find where to start collapsing (first tool call)
      const firstToolCallIndex = filteredBlocks.findIndex(b => isToolCallsBlock(b));

      return (
        <div className="content-blocks">
          {/* Blocks before any tool calls (e.g., plan) */}
          {filteredBlocks.slice(0, firstToolCallIndex).map((block) => renderContentBlock(block))}

          {/* Collapsible section: everything from first tool call to before latest tool call */}
          <ToolHistoryCollapsible
            blocks={filteredBlocks.slice(firstToolCallIndex, latestToolCallIndex)}
            collapseUntilIndex={filteredBlocks.slice(firstToolCallIndex, latestToolCallIndex).length}
            renderContentBlock={renderContentBlock}
          />

          {/* Latest tool call and everything after (always visible) */}
          {filteredBlocks.slice(latestToolCallIndex).map((block) => renderContentBlock(block))}
        </div>
      );
    }

    return (
      <div className="content-blocks">
        {filteredBlocks.map((block) => renderContentBlock(block))}
      </div>
    );
  };

  return (
    <div className="message-content min-w-0">
      {renderContent()}
    </div>
  );
};
