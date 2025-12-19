import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message, ContentBlock, isTextBlock, isToolCallsBlock, isExplorerBlock, isVisualizationsBlock, isPlanBlock, isErrorBlock } from '@/types/chat';
import { ExplorerMessage } from '@/components/messages/ExplorerMessage';
import { markdownComponents } from '@/utils/markdownComponents';
import VisualizationMessage from '@/components/messages/VisualizationMessage';
import { ToolCallMessage } from '@/components/messages/ToolCallMessage';
import { PlanMessage } from '@/components/messages/PlanMessage';
import { ErrorMessage } from '@/components/messages/ErrorMessage';
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
            className="w-full flex items-center gap-2 p-2 mb-2 rounded-lg border border-border bg-background hover:bg-accent hover:text-accent-foreground transition-colors text-left"
            type="button"
          >
            {isExpanded ? (
              <ChevronDown className="w-4 h-4 flex-shrink-0 transition-transform duration-200" />
            ) : (
              <ChevronRight className="w-4 h-4 flex-shrink-0 transition-transform duration-200" />
            )}
            <span className="font-semibold text-foreground">
              Previous steps ({toolNames.length} tools)
            </span>
          </button>
        </CollapsibleTrigger>

        {!isExpanded && (
          <div className="mb-2 ml-6 space-y-1 animate-in fade-in-0 duration-200">
            <ul className="list-disc list-inside space-y-0.5">
              {toolNames.map((name, index) => (
                <li key={index} className="text-sm text-muted-foreground">
                  {name}
                </li>
              ))}
            </ul>
          </div>
        )}

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

export const MessageRenderer: React.FC<MessageRendererProps> = ({ message, onAction }) => {
  const renderContentBlock = (block: ContentBlock) => {
    if (isTextBlock(block)) {
      return (
        <div key={block.id} className="content-block text-block">
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
        status: toolCall.status
      }));

      return (
        <div key={block.id} className="content-block tool-calls-block mb-4">
          <ToolCallMessage
            toolCalls={mappedToolCalls}
            content={block.data.content}
            needsApproval={block.needsApproval}
            onApprove={onAction ? () => onAction('approveToolCall', block) : undefined}
            onReject={onAction ? () => onAction('rejectToolCall', block) : undefined}
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
      return (
        <div key={block.id} className="content-block plan-block mb-4">
          <PlanMessage
            plan={block.data.plan}
            needsApproval={block.needsApproval}
            onApprove={onAction ? () => onAction('approvePlan', block) : undefined}
            onReject={onAction ? () => onAction('rejectPlan', block) : undefined}
          />
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
          if (index < toolCallsIndex && toolCallsContent && textContent.trim()) {
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

    // Collapse everything before the latest tool call block (if any exists)
    const latestToolCallIndex = filteredBlocks.reduce((acc, block, index) => (
      isToolCallsBlock(block) ? index : acc
    ), -1);

    const hasHistoryBeforeLatestToolCall = latestToolCallIndex > 0;

    if (hasHistoryBeforeLatestToolCall) {
      return (
        <ToolHistoryCollapsible
          blocks={filteredBlocks}
          collapseUntilIndex={latestToolCallIndex}
          renderContentBlock={renderContentBlock}
        />
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
