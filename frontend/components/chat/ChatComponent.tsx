'use client'

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { ThumbsUp, ThumbsDown, ChevronDown } from 'lucide-react';
import { Message as MessageType, ChatComponentProps, HandlerResponse, ContentBlock, ToolCallsContent, createTextBlock, createToolCallsBlock, createExplorerBlock, createVisualizationsBlock, createPlanBlock, createErrorBlock, createExplanationBlock, createReasoningChainBlock } from '@/types/chat';
import Message from './Message';
import GeneratingIndicator from './GeneratingIndicator';
import InputForm from './InputForm';
import ThreadTitle from '../ThreadTitle';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import GraphFlowPanel from '../graph-flow/GraphFlowPanel';


const EphemeralToolIndicator: React.FC<{
  steps: Array<{
    name: string;
    id: string;
    startTime: number;
    endTime?: number;
    status: 'calling' | 'completed';
  }>
}> = ({ steps }) => {
  return (
    <div className="bg-muted border-l-4 border-border p-3 mb-2 rounded-r-lg">
      <div className="space-y-2">
        {steps.map((step, index) => (
          <div key={step.id} className="flex items-center gap-2 text-sm">
            {step.status === 'completed' ? (
              <div className="w-3 h-3 bg-foreground rounded-full flex-shrink-0 flex items-center justify-center">
                <span className="text-background text-xs">✓</span>
              </div>
            ) : (
              <div className="w-3 h-3 border-2 border-foreground border-t-transparent rounded-full animate-spin flex-shrink-0" />
            )}
            <span className={`font-medium ${step.status === 'completed' ? 'text-foreground' : 'text-muted-foreground'}`}>
              {step.status === 'completed'
                ? `Step ${index + 1}: ${step.name || 'Unknown Tool'} (completed)`
                : `Step ${index + 1}: ${step.name || 'Unknown Tool'}...`
              }
            </span>
            <span className={`text-xs ${step.status === 'completed' ? 'text-muted-foreground' : 'text-muted-foreground'}`}>
              {step.status === 'completed'
                ? `${Math.max(1, Math.floor((step.endTime! - step.startTime) / 1000))}s`
                : `${Math.floor((Date.now() - step.startTime) / 1000)}s`
              }
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

const ChatComponent: React.FC<ChatComponentProps> = ({
  onSendMessage,
  onApprove,
  onFeedback,
  onCancel,
  onRetry,
  currentThreadId,
  initialMessages = [],
  className = "",
  placeholder = "Type your message...",
  disabled = false,
  onMessageUpdated,
  threadTitle,
  onTitleChange,
  sidebarExpanded = false,
  hasDataContext,
  onOpenDataContext,
  onDataFrameDetected,
  onCancelStream,
  onToggleGraphPanel,
  graphPanelOpen = false,
  graphStructure,
}) => {


  // Local state for loading and execution
  const [isLoading, setIsLoading] = useState(false);
  const [executionStatus, setExecutionStatus] = useState<'idle' | 'running' | 'user_feedback' | 'error'>('idle');
  const [useStreaming, setUseStreaming] = useState(true);

  const [messages, setMessages] = useState<MessageType[]>(initialMessages);
  const [inputValue, setInputValue] = useState<string>('');
  const [pendingApproval, setPendingApproval] = useState<string | null>(null); // Block ID, not message ID
  const [isAtBottom, setIsAtBottom] = useState<boolean>(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  // Streaming UI state
  const [streamingActive, setStreamingActive] = useState<boolean>(false);
  const [hasReceivedContent, setHasReceivedContent] = useState<boolean>(false);

  // Enhanced input state
  const [usePlanning, setUsePlanning] = useState<boolean>(false);
  const [useExplainer, setUseExplainer] = useState<boolean>(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);

  // Tool call state for ephemeral indicators - now tracks step history
  const [toolStepHistory, setToolStepHistory] = useState<{
    messageId: string;
    steps: Array<{
      name: string;
      id: string;
      startTime: number;
      endTime?: number;
      status: 'calling' | 'completed';
    }>;
  } | null>(null);

  // Use shared state
  const contextThreadId = currentThreadId;
  const showApprovalButtons = pendingApproval !== null && executionStatus === 'user_feedback';
  const messagesRef = useRef<MessageType[]>([]);

  // Mapping between backend assistant_message_id and frontend message IDs
  // This allows content_block events with backend message_id to update the correct frontend message
  const backendToFrontendMessageIdMap = useRef<Map<string, string>>(new Map());


  const getLatestAssistantMessageId = (): string | null => {
    // Iterate through messages in reverse to find the most recent assistant message
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].sender === 'assistant') {
        return messages[i].message_id;
      }
    }
    return null;
  };



  // Check if user is near the bottom of the messages container
  const checkIfNearBottom = (): boolean => {
    const container = messagesContainerRef.current;
    if (!container) return true;

    const threshold = 100; // pixels from bottom
    const scrollTop = container.scrollTop;
    const scrollHeight = container.scrollHeight;
    const clientHeight = container.clientHeight;

    return scrollHeight - scrollTop - clientHeight < threshold;
  };

  const scrollToBottom = (): void => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    // Update isAtBottom state after scrolling
    setTimeout(() => {
      setIsAtBottom(checkIfNearBottom());
    }, 100);
  };

  // Track scroll position to show/hide scroll-to-bottom button
  // This effect runs once and keeps the scroll listener active
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) {
      // If container doesn't exist yet, check again after a short delay
      const timeoutId = setTimeout(() => {
        const retryContainer = messagesContainerRef.current;
        if (retryContainer) {
          setIsAtBottom(checkIfNearBottom());
        }
      }, 100);
      return () => clearTimeout(timeoutId);
    }

    const handleScroll = () => {
      setIsAtBottom(checkIfNearBottom());
    };

    container.addEventListener('scroll', handleScroll);
    // Check initial position
    handleScroll();

    return () => {
      container.removeEventListener('scroll', handleScroll);
    };
  }, []); // Empty deps - only register once, scroll handler uses checkIfNearBottom which reads from ref

  // Also check scroll position when messages change
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (container && messages.length > 0) {
      // Small delay to ensure DOM is updated
      const timeoutId = setTimeout(() => {
        setIsAtBottom(checkIfNearBottom());
      }, 100);
      return () => clearTimeout(timeoutId);
    } else if (messages.length === 0) {
      setIsAtBottom(false);
    }
  }, [messages.length]);

  // Auto-scroll during streaming when user is near bottom
  // This triggers on messages changes (including content block updates) and scroll position
  useEffect(() => {
    if (streamingActive && messages.length > 0) {
      // Check if user is near bottom before scrolling
      const nearBottom = checkIfNearBottom();

      if (nearBottom) {
        // Small delay to ensure DOM is updated with new content
        const timeoutId = setTimeout(() => {
          // Use instant scrolling during streaming for better performance
          messagesEndRef.current?.scrollIntoView({ behavior: 'instant' });
          // Update isAtBottom state after scrolling
          setIsAtBottom(true);
        }, 50);
        return () => clearTimeout(timeoutId);
      } else {
        // User scrolled up, update state
        setIsAtBottom(false);
      }
    }
  }, [messages, streamingActive]); // Trigger on any messages change

  // Additional effect to handle rapid content updates during streaming
  // This ensures scroll happens even when messages array reference doesn't change
  useEffect(() => {
    if (streamingActive && isAtBottom) {
      const scrollInterval = setInterval(() => {
        const nearBottom = checkIfNearBottom();
        if (nearBottom) {
          messagesEndRef.current?.scrollIntoView({ behavior: 'instant' });
        }
      }, 100); // Check every 100ms during streaming

      return () => clearInterval(scrollInterval);
    }
  }, [streamingActive, isAtBottom]);

  // Auto-scroll for new non-streaming messages (only if near bottom)
  useEffect(() => {
    if (!streamingActive && messages.length > 0 && isAtBottom) {
      const timeoutId = setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
      return () => clearTimeout(timeoutId);
    }
  }, [messages.length, streamingActive, isAtBottom]);

  // Mirror messages into a ref for post-await access
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);


  // Helper function to set pendingApproval from a message's first block that needs approval
  const setPendingApprovalFromMessage = useCallback((message: MessageType | undefined) => {
    if (!message || !Array.isArray(message.content) || message.content.length === 0) {
      return;
    }

    // Find a block that has needsApproval (block-level only)
    const blockNeedingApproval = message.content.find(block => block.needsApproval === true);

    if (blockNeedingApproval) {
      setPendingApproval(blockNeedingApproval.id);
    }
  }, []);


  useEffect(() => {
    if (!pendingApproval && messages.length > 0) {
      // Find any message with a block that needs approval (block-level only)
      for (const message of messages) {
        if (Array.isArray(message.content) && message.content.some(block => block.needsApproval === true)) {
          setPendingApprovalFromMessage(message);
          break;
        }
      }
    }
  }, [messages, pendingApproval, setPendingApprovalFromMessage]);

  // Ensure pendingApproval always references an existing block ID
  useEffect(() => {
    if (!pendingApproval) return;

    const blockExists = messages.some(message =>
      Array.isArray(message.content) &&
      message.content.some(block => block.id === pendingApproval)
    );

    if (!blockExists) {
      setPendingApproval(null);
      for (const msg of messages) {
        if (Array.isArray(msg.content) && msg.content.some(block => block.needsApproval)) {
          setPendingApprovalFromMessage(msg);
          break;
        }
      }
    }
  }, [messages, pendingApproval, setPendingApprovalFromMessage]);


  // Memoize initialMessages to prevent unnecessary re-renders
  const memoizedInitialMessages = useMemo(() => initialMessages, [
    initialMessages.length,
    initialMessages.map(m => m.message_id).join(','),
    initialMessages.map(m => m.content).join(',')
  ]);

  // Update messages when initialMessages prop changes
  useEffect(() => {
    setMessages(memoizedInitialMessages);
  }, [memoizedInitialMessages]);

  // Separate method for creating explorer messages (as suggested)
  const createExplorerMessage = useCallback((response: HandlerResponse): void => {
    if (!response.explorerData) return;

    const explorerMessageId = response.explorerMessageId || (Date.now() + Math.floor(Math.random() * 1000)).toString();
    const explorerMessage: MessageType = {
      message_id: explorerMessageId,
      sender: 'assistant',
      content: response.message ? [createTextBlock(`text_${explorerMessageId}`, response.message, false)] : [],
      timestamp: new Date(),
      checkpointId: response.explorerData.checkpoint_id,
      metadata: { explorerData: response.explorerData },
      threadId: contextThreadId || currentThreadId || undefined
    };

    // Add explorer message after a short delay to ensure proper ordering
    setTimeout(() => {
      setMessages(prev => [...prev, explorerMessage]);
    }, 50);
  }, [contextThreadId, currentThreadId]);
  // Helper function to handle response and create special messages if needed
  const handleResponse = useCallback((response: HandlerResponse): string => {
    if (response.explorerData) {
      createExplorerMessage(response);
    }
    if (response.visualizations && response.visualizations.length > 0) {
      const vizMessageId = response.visualizationMessageId || (Date.now() + Math.floor(Math.random() * 1000) + 10000).toString();
      const vizMessage: MessageType = {
        message_id: vizMessageId,
        sender: 'assistant',
        content: response.message ? [createTextBlock(`text_${vizMessageId}`, response.message, false)] : [],
        timestamp: new Date(),
        checkpointId: response.checkpoint_id, // Add checkpoint ID for visualization messages
        metadata: { visualizations: response.visualizations },
        threadId: contextThreadId || currentThreadId || undefined
      };
      setTimeout(() => {
        setMessages(prev => [...prev, vizMessage]);
      }, 50);
    }
    return response.message;
  }, [createExplorerMessage, contextThreadId, currentThreadId]);


  // Helper function to handle streaming errors
  const handleStreamingError = useCallback((
    streamErr: Error,
    streamingMsgId: string
  ) => {
    setMessages(prev => prev.map(m =>
      m.message_id === streamingMsgId
        ? { ...m, content: [createTextBlock(`error_${streamingMsgId}`, `Error: ${streamErr.message || 'Streaming failed'}`, false)], isStreaming: false }
        : m
    ));
  }, []);

  // Helper function to check if error is timeout
  const isTimeoutError = useCallback((error: Error) => {
    const errorMsg = error.message || 'Something went wrong';
    return errorMsg.includes('timeout') ||
      errorMsg.includes('30000ms exceeded') ||
      errorMsg.includes('Request timed out') ||
      errorMsg.includes('ECONNABORTED') ||
      (error as any)?.code === 'ECONNABORTED';
  }, []);

  // Helper function to update message properties
  const updateMessage = useCallback((
    messageId: string,
    updates: Partial<MessageType>
  ) => {
    setMessages(prev => prev.map(m =>
      m.message_id === messageId ? { ...m, ...updates } : m
    ));
  }, []);

  // Helper function to update message flags and trigger callback
  const updateMessageFlags = useCallback(async (
    messageId: string,
    updates: Partial<MessageType>
  ) => {
    // Get the current message before updating
    const currentMessage = messages.find(m => m.message_id === messageId);
    if (!currentMessage) {
      console.warn('Message not found for update:', messageId);
      return;
    }

    // Update the local state
    updateMessage(messageId, updates);

    // Trigger the callback if provided - parent will handle persistence
    if (onMessageUpdated) {
      const updatedMessage = { ...currentMessage, ...updates };
      onMessageUpdated(updatedMessage);
    }
  }, [updateMessage, onMessageUpdated, messages]);

  // Helper function to handle tool events
  const handleToolEvents = useCallback((
    status: string,
    eventData: string | undefined,
    streamingMsgId: string
  ) => {
    // Handle tool call start - show temporary indicator
    if (status === 'tool_call' && eventData) {
      try {
        const toolData = JSON.parse(eventData);
        const toolId = toolData.tool_id;
        const toolName = toolData.tool_name || 'Unknown Tool';

        // Only add to indicator if we have a real tool_id (not temp key)
        if (toolId && !toolId.toString().startsWith('temp_')) {
          setToolStepHistory(prev => {
            if (!prev || prev.messageId !== streamingMsgId) {
              // Create new history
              return {
                messageId: streamingMsgId,
                steps: [{
                  name: toolName,
                  id: toolId,
                  startTime: Date.now(),
                  status: 'calling' as const
                }]
              };
            }

            // Check if step already exists
            const existingStep = prev.steps.find(s => s.id === toolId);

            if (existingStep) {
              // Update existing step (for incremental updates)
              const updatedSteps = prev.steps.map(step =>
                step.id === toolId ? { ...step, name: toolName } : step
              );
              return { ...prev, steps: updatedSteps };
            } else {
              // Add new step
              return {
                ...prev,
                steps: [...prev.steps, {
                  name: toolName,
                  id: toolId,
                  startTime: Date.now(),
                  status: 'calling' as const
                }]
              };
            }
          });
        }
      } catch (error) {
        console.error('Error handling tool_call for indicator:', error);
      }
    }

    // Handle SQL Approval interrupt
    if (status === 'interrupt') {
      try {
        if (!eventData) return;
        const interruptData = JSON.parse(eventData);

        // Special handling for sql_approval
        if (interruptData.value && interruptData.value.type === 'sql_approval') {
          const sqlApprovalMsgId = (Date.now() + Math.floor(Math.random() * 1000)).toString();

          const sqlBlock: ContentBlock = {
            id: `sql_approval_${sqlApprovalMsgId}`,
            type: 'text',
            needsApproval: true,
            metadata: {
              type: 'sql_approval',
              sql: interruptData.value.sql,
              tool_call_id: interruptData.value.tool_call_id
            },
            data: {
              text: interruptData.value.description || "Please review the generated SQL."
            }
          };

          const message: MessageType = {
            message_id: sqlApprovalMsgId,
            sender: 'assistant',
            content: [sqlBlock],
            timestamp: new Date(),
            threadId: contextThreadId || currentThreadId || undefined
          };

          setTimeout(() => {
            setMessages(prev => [...prev, message]);
          }, 50);

          setExecutionStatus('user_feedback');
        }
      } catch (e) {
        console.error('Error handling interrupt:', e);
      }
    }

    // Handle tool result - update the indicator
    if (status === 'tool_result' && eventData) {
      try {
        const resultData = JSON.parse(eventData);
        const toolCallId = resultData.tool_call_id;

        setToolStepHistory(prev => {
          if (!prev || prev.messageId !== streamingMsgId) return prev;

          const updatedSteps = prev.steps.map(step =>
            step.id === toolCallId
              ? { ...step, status: 'completed' as const, endTime: Date.now() }
              : step
          );
          return { ...prev, steps: updatedSteps };
        });
      } catch (error) {
        console.error('Error handling tool_result for indicator:', error);
      }
    }
  }, [contextThreadId, currentThreadId]);

  // Helper function to resolve backend message ID to frontend message ID
  const resolveMessageId = useCallback((frontendMessageId: string, backendMessageId?: string): string => {
    // If backendMessageId is provided, try to resolve it to a frontend message ID
    if (backendMessageId !== undefined && backendMessageId !== null) {
      const mappedId = backendToFrontendMessageIdMap.current.get(backendMessageId);
      if (mappedId !== undefined) {
        return mappedId;
      }
    }
    // Fall back to the provided frontend message ID
    return frontendMessageId;
  }, []);


  const updateContentBlocksCallback = useCallback(
    (messageId: string, contentBlocks?: ContentBlock[]): void => {
      setMessages(prev =>
        prev.map(m => {
          if (m.message_id === messageId) {
            if (!contentBlocks || contentBlocks.length === 0) {
              return { ...m, content: [] };
            }

            // Merge blocks: update existing by ID, append new ones
            const existingBlocks = Array.isArray(m.content) ? m.content : [];
            const existingBlockIds = new Set(existingBlocks.map(b => b.id));
            const newBlockIds = new Set(contentBlocks.map(b => b.id));

            // Keep existing blocks that aren't being updated
            const preservedBlocks = existingBlocks.filter(b => !newBlockIds.has(b.id));

            // Add all new/updated blocks
            const mergedBlocks = [...preservedBlocks, ...contentBlocks];

            return { ...m, content: mergedBlocks };
          }
          return m;
        })
      );
    },
    []
  );

  // Shared handler for content_block events
  const handleContentBlockEvent = useCallback((
    eventData: string,
    streamingMsgId: string,
    currentContentBlocks: ContentBlock[]
  ): ContentBlock[] => {
    try {
      // Mark that we've received content from the stream
      setHasReceivedContent(true);
      setIsLoading(false);

      const blockData = JSON.parse(eventData);
      const blockType = blockData.block_type;
      const blockId = blockData.block_id;
      const action = blockData.action;
      // Always use streamingMsgId for this message, ignore backend message_id
      // This ensures all blocks go to the same frontend message

      let updatedBlocks = [...currentContentBlocks];

      if (blockType === 'text') {
        if (action === 'append_text') {
          let textBlock = updatedBlocks.find(b => b.id === blockId);
          if (!textBlock) {
            textBlock = createTextBlock(blockId, '', false);
            updatedBlocks = [...updatedBlocks, textBlock];
          }
          (textBlock.data as any).text += blockData.content;
        } else if (action === 'finalize_text') {
          // First, try to find the block by the finalized block ID
          let textBlock = updatedBlocks.find(b => b.id === blockId);

          if (!textBlock) {
            // Block not found with finalized ID - it might be using a streaming ID
            // Look for a text block with a different ID (likely text_run--*)
            const streamingTextBlock = updatedBlocks.find(b => b.type === 'text' && b.id.startsWith('text_run--'));

            if (streamingTextBlock) {
              // Update the streaming block's ID to match the finalized ID
              // This ensures approval uses the correct ID that was saved to the database
              streamingTextBlock.id = blockId;
              (streamingTextBlock.data as any).text = blockData.content;
              textBlock = streamingTextBlock;
            } else {
              // No streaming block found, create a new one with the finalized ID
              textBlock = createTextBlock(blockId, blockData.content, false);
              updatedBlocks = [...updatedBlocks, textBlock];
            }
          } else {
            // Block found with finalized ID, just update the content
            (textBlock.data as any).text = blockData.content;
          }
        }
      } else if (blockType === 'plan') {
        // Handle plan blocks from planner node
        if (action === 'add_planner') {
          // Create or update plan block
          let planBlock = updatedBlocks.find(b => b.id === blockId);
          if (!planBlock) {
            planBlock = createPlanBlock(blockId, blockData.content, false);
            updatedBlocks = [...updatedBlocks, planBlock];
          } else {
            // Update existing plan block
            (planBlock.data as any).plan = blockData.content;
          }
        } else if (action === 'replan') {
          setMessages(prev => prev.map(msg => ({
            ...msg,
            content: Array.isArray(msg.content)
              ? msg.content.map(block =>
                block.type === 'plan'
                  ? { ...block, needsApproval: false }
                  : block
              )
              : msg.content
          })));
          updatedBlocks = updatedBlocks.map(block =>
            block.type === 'plan'
              ? { ...block, needsApproval: false }
              : block
          );

          let planBlock = updatedBlocks.find(b => b.id === blockId);
          if (!planBlock) {
            planBlock = createPlanBlock(blockId, blockData.content, true);
            updatedBlocks = [...updatedBlocks, planBlock];
          } else {
            (planBlock.data as any).plan = blockData.content;
            planBlock.needsApproval = true;
          }
        }
      } else if (blockType === 'tool_calls') {

        const blockIdFromBackend = blockData.block_id || `tool_calls_${streamingMsgId}`;
        let consolidatedBlock = updatedBlocks.find(b => b.id === blockIdFromBackend && b.type === 'tool_calls');

        if (action === 'stream_args') {
          if (!consolidatedBlock) {
            const toolCall = {
              name: blockData.tool_name,
              input: {},
              status: 'pending' as const
            };
            consolidatedBlock = createToolCallsBlock(blockIdFromBackend, [toolCall], false);
            updatedBlocks = [...updatedBlocks, consolidatedBlock];
          }

          const toolCallsData = { ...consolidatedBlock.data } as ToolCallsContent;
          let toolCallIndex = toolCallsData.toolCalls.findIndex(tc => tc.name === blockData.tool_name);

          if (toolCallIndex < 0) {
            toolCallsData.toolCalls.push({
              name: blockData.tool_name,
              input: {},
              status: 'pending' as const
            });
            toolCallIndex = toolCallsData.toolCalls.length - 1;
          }

          const existingArgs = (toolCallsData.toolCalls[toolCallIndex] as any)._argsBuffer || '';
          const accumulatedArgs = existingArgs + (blockData.args_chunk || '');
          (toolCallsData.toolCalls[toolCallIndex] as any)._argsBuffer = accumulatedArgs;

          try {
            const parsedInput = JSON.parse(accumulatedArgs);

            const updatedToolCalls = [...toolCallsData.toolCalls];
            updatedToolCalls[toolCallIndex] = {
              ...updatedToolCalls[toolCallIndex],
              input: parsedInput,
              _argsBuffer: accumulatedArgs
            } as any;

            const updatedToolCallsData: ToolCallsContent = {
              ...toolCallsData,
              toolCalls: updatedToolCalls
            };

            updatedBlocks = updatedBlocks.map(block =>
              block.id === blockIdFromBackend
                ? { ...block, data: updatedToolCallsData }
                : block
            );

            updateContentBlocksCallback(streamingMsgId, updatedBlocks);
          } catch (e) {
          }
        } else if (action === 'update_tool_calls_explanation') {
          if (!consolidatedBlock) {
            const newToolCallsBlock = createToolCallsBlock(blockIdFromBackend, [], false);
            (newToolCallsBlock.data as ToolCallsContent).content = '';
            consolidatedBlock = newToolCallsBlock;
            updatedBlocks = [...updatedBlocks, consolidatedBlock];
          }

          const toolCallsData = { ...consolidatedBlock.data } as ToolCallsContent;
          const existing = typeof toolCallsData.content === 'string' ? toolCallsData.content : '';
          toolCallsData.content = existing + (blockData.content || '');
          updatedBlocks = updatedBlocks.map(block =>
            block.id === blockIdFromBackend
              ? { ...block, data: toolCallsData }
              : block
          );
        } else if (action === 'add_tool_call') {
          const parsedArgs = blockData.args ? JSON.parse(blockData.args) : {};

          if (!consolidatedBlock) {
            const toolCall = {
              name: blockData.tool_name,
              input: parsedArgs || {},
              status: 'pending' as const
            };
            consolidatedBlock = createToolCallsBlock(blockIdFromBackend, [toolCall], false);
            updatedBlocks = [...updatedBlocks, consolidatedBlock];
          } else {
            const toolCallsData = { ...consolidatedBlock.data } as ToolCallsContent;
            const existingToolCallIndex = toolCallsData.toolCalls.findIndex(tc => tc.name === blockData.tool_name);

            if (existingToolCallIndex >= 0) {
              const existingInput = toolCallsData.toolCalls[existingToolCallIndex].input;
              const newInput = (parsedArgs && Object.keys(parsedArgs).length > 0) ? parsedArgs : existingInput;
              toolCallsData.toolCalls = [
                ...toolCallsData.toolCalls.slice(0, existingToolCallIndex),
                { ...toolCallsData.toolCalls[existingToolCallIndex], input: newInput },
                ...toolCallsData.toolCalls.slice(existingToolCallIndex + 1)
              ];
            } else {
              toolCallsData.toolCalls = [
                ...toolCallsData.toolCalls,
                {
                  name: blockData.tool_name,
                  input: parsedArgs || {},
                  status: 'pending' as const
                }
              ];
            }

            updatedBlocks = updatedBlocks.map(block =>
              block.id === blockIdFromBackend
                ? { ...block, data: toolCallsData }
                : block
            );
          }
        } else if (action === 'update_tool_result') {
          if (consolidatedBlock) {
            const toolCallsData = { ...consolidatedBlock.data } as ToolCallsContent;
            const toolCallIndex = toolCallsData.toolCalls.findIndex(tc => tc.name === blockData.tool_name);
            if (toolCallIndex >= 0) {
              const existingToolCall = toolCallsData.toolCalls[toolCallIndex];
              const finalInput = (blockData.input && Object.keys(blockData.input).length > 0)
                ? blockData.input
                : (existingToolCall.input && Object.keys(existingToolCall.input).length > 0
                  ? existingToolCall.input
                  : {});

              const updatedToolCall = {
                ...existingToolCall,
                input: finalInput,
                output: blockData.output,
                status: 'approved' as const
              };

              toolCallsData.toolCalls = [
                ...toolCallsData.toolCalls.slice(0, toolCallIndex),
                updatedToolCall,
                ...toolCallsData.toolCalls.slice(toolCallIndex + 1)
              ];

              updatedBlocks = updatedBlocks.map(block =>
                block.id === blockIdFromBackend
                  ? { ...block, data: toolCallsData }
                  : block
              );

              updateContentBlocksCallback(streamingMsgId, updatedBlocks);

              // Detect DataFrame context in tool output
              if (onDataFrameDetected && blockData.output) {
                try {
                  // Parse output if it's a string
                  const output = typeof blockData.output === 'string'
                    ? JSON.parse(blockData.output)
                    : blockData.output;

                  // Check for data_context.df_id
                  if (output?.data_context?.df_id) {
                    console.log('DataFrame detected:', output.data_context.df_id);
                    onDataFrameDetected(output.data_context.df_id);
                  }
                } catch (e) {
                  // Output is not JSON or doesn't contain data_context, ignore
                }
              }
            }
          }

          handleToolEvents('tool_result', eventData, streamingMsgId);
        }
      } else if (blockType === 'explorer' && action === 'add_explorer') {
        const explorerData = {
          steps: blockData.steps || [],
          final_result: blockData.final_result || {},
          overall_confidence: blockData.overall_confidence || 0,
          checkpoint_id: blockData.checkpoint_id,
          query: blockData.query || '',
          run_status: 'finished'
        };
        const explorerBlock = createExplorerBlock(blockId, blockData.checkpoint_id, false, explorerData);
        updatedBlocks = [...updatedBlocks, explorerBlock];
      } else if (blockType === 'visualizations' && action === 'add_visualizations') {
        const visualizations = blockData.visualizations || [];
        const vizBlock = createVisualizationsBlock(blockId, blockData.checkpoint_id, false, visualizations);
        updatedBlocks = [...updatedBlocks, vizBlock];
      } else if (blockType === 'error' && action === 'add_error') {
        const errorExplanation = blockData.error_explanation;
        if (errorExplanation) {
          const errorBlock = createErrorBlock(blockId, errorExplanation);
          updatedBlocks = [...updatedBlocks, errorBlock];
        }
      } else if (blockType === 'explanation' && action === 'add_block') {
        // Handle explanation blocks from explain node
        const explanationData = blockData.data;
        if (explanationData) {
          const explanationBlock = createExplanationBlock(blockId, explanationData);
          updatedBlocks = [...updatedBlocks, explanationBlock];
        }
      } else if (blockType === 'reasoning_chain' && action === 'add_block') {
        // Handle reasoning chain blocks from joiner node
        const chainData = blockData.data;
        if (chainData && chainData.steps) {
          const reasoningChainBlock = createReasoningChainBlock(blockId, chainData);
          updatedBlocks = [...updatedBlocks, reasoningChainBlock];
        }
      }

      // Update the message with current content blocks
      updateContentBlocksCallback(streamingMsgId, updatedBlocks);

      if (blockType === 'tool_calls') {
        handleToolEvents('tool_call', eventData, streamingMsgId);
      }

      return updatedBlocks;
    } catch (error) {
      console.error('Error handling content_block event:', error);
      return currentContentBlocks;
    }
  }, [resolveMessageId, updateContentBlocksCallback, handleToolEvents]);


  const handleSend = async (): Promise<void> => {
    if (!inputValue.trim() || isLoading || disabled || streamingActive) return;

    // Force scroll to bottom when user sends a message
    scrollToBottom();

    const userMessage = inputValue.trim();

    // If there's a pending approval, treat this as feedback
    if (pendingApproval) {
      const message = messages.find(m =>
        Array.isArray(m.content) && m.content.some(block => block.id === pendingApproval)
      );
      if (!message) return;

      // Add feedback as a user message
      const feedbackMessageId = Date.now().toString();
      const feedbackMessage: MessageType = {
        message_id: feedbackMessageId,
        sender: 'user',
        content: [createTextBlock(`text_${feedbackMessageId}`, userMessage, false)],
        timestamp: new Date()
      };

      setMessages(prev => [...prev, feedbackMessage]);
      setInputValue('');

      // Call the feedback handler
      if (onFeedback && message.message_id) {
        const result = await onFeedback(message.message_id, userMessage, message);
        // Handle the result similar to handleSendFeedback
        if (result) {
          if ((result as HandlerResponse).isStreaming && (result as HandlerResponse).streamingHandler) {
            const backendStreamId = (result as HandlerResponse).backendMessageId;
            const streamingMsgId = (backendStreamId && typeof backendStreamId === 'string')
              ? backendStreamId
              : Date.now().toString();

            const existingMessageIndex = messages.findIndex(m => m.message_id === streamingMsgId);

            if (existingMessageIndex !== -1) {
              setMessages(prev => prev.map((m, idx) =>
                idx === existingMessageIndex
                  ? {
                    ...m,
                    isStreaming: true,
                    needsApproval: false
                  }
                  : m
              ));
            } else {
              // Message doesn't exist - create new one
              const streamingMessage: MessageType = {
                message_id: streamingMsgId,
                sender: 'assistant',
                content: [], // Initialize with empty content blocks array
                timestamp: new Date(),
                isStreaming: true
              };
              setMessages(prev => [...prev, streamingMessage]);
            }

            setStreamingActive(true);
            setPendingApproval(null);

            let currentContentBlocks: ContentBlock[] = [];

            await (result as HandlerResponse).streamingHandler!(streamingMsgId, updateContentBlocksCallback, (status, eventData, responseType) => {
              if (!status) return;

              // Handle content_block events (for replan, answer, etc.)
              if (status === 'content_block' && eventData) {
                currentContentBlocks = handleContentBlockEvent(
                  eventData,
                  streamingMsgId,
                  currentContentBlocks
                );
                return;
              }

              // Handle tool events
              handleToolEvents(status, eventData, streamingMsgId);

              // Handle streaming status updates
              if (status === 'finished' || status === 'user_feedback') {
                setToolStepHistory(null);

                // Update execution status to match streaming status
                setExecutionStatus(status === 'finished' ? 'idle' : status);

                setMessages(prev => prev.map(m =>
                  m.message_id === streamingMsgId
                    ? {
                      ...m,
                      isStreaming: status !== 'finished',
                      needsApproval: status === 'user_feedback' && (responseType === 'replan' || responseType === undefined)
                    }
                    : m
                ));

                if (status === 'user_feedback' && (responseType === 'replan' || responseType === undefined)) {
                  // Find the first block that needs approval in the streaming message
                  // Use messagesRef to get the latest state
                  const streamingMessage = messagesRef.current.find(m => m.message_id === streamingMsgId);
                  setPendingApprovalFromMessage(streamingMessage);
                }
              }
            });
            setStreamingActive(false);
          } else {
            // Use backend message ID if available, otherwise generate one
            const backendUuid = (result as HandlerResponse).backendMessageId;
            const tempId = Date.now().toString();

            const assistantMessage: MessageType = {
              message_id: backendUuid || tempId, // Store UUID from backend
              sender: 'assistant',
              content: (result as HandlerResponse).message ? [createTextBlock(`text_${tempId}`, (result as HandlerResponse).message || 'Response received', false)] : [],
              timestamp: new Date()
            };
            setMessages(prev => [...prev, assistantMessage]);
            // Check if any block needs approval (block-level only)
            const hasBlockNeedingApproval = Array.isArray(assistantMessage.content) &&
              assistantMessage.content.some(block => block.needsApproval === true);
            if (hasBlockNeedingApproval) {
              setPendingApprovalFromMessage(assistantMessage);
            } else {
              setPendingApproval(null);
            }
          }
        }
      }
      return;
    }

    // Regular message handling
    setInputValue('');
    setPendingApproval(null);

    const tempUserId = Date.now().toString();
    const newUserMessage: MessageType = {
      message_id: tempUserId,
      sender: 'user',
      content: [createTextBlock(`text_${tempUserId}`, userMessage, false)],
      timestamp: new Date(),
      threadId: contextThreadId || currentThreadId || undefined,
      metadata: {
        attachedFiles: attachedFiles
      }
    };

    setMessages(prev => [...prev, newUserMessage]);
    setIsLoading(true);


    try {
      const response = await onSendMessage(userMessage, messages, { usePlanning, useExplainer, attachedFiles });
      if (response.isStreaming && response.streamingHandler) {

        const streamingMsgId = response.backendMessageId || Date.now().toString();
        const streamingMessage: MessageType = {
          message_id: streamingMsgId,
          sender: 'assistant',
          content: [],
          timestamp: new Date(),
          threadId: contextThreadId || currentThreadId || undefined,
          isStreaming: true
        } as any;
        setMessages(prev => [...prev, streamingMessage]);
        setStreamingActive(true);
        setHasReceivedContent(false);
        setExecutionStatus('running');

        try {

          let currentContentBlocks: ContentBlock[] = [];

          await response.streamingHandler(streamingMsgId, updateContentBlocksCallback, (status, eventData, responseType) => {
            if (!status) return;

            // Handle graph node events for visualization
            if (status === 'graph_node' && eventData) {
              try {
                const graphNodeData = JSON.parse(eventData);
                if (typeof window !== 'undefined' && (window as any).handleGraphNodeEvent) {
                  (window as any).handleGraphNodeEvent(graphNodeData);
                }
              } catch (error) {
                console.error('Error handling graph_node event:', error);
              }
              return;
            }

            if (status === 'content_block' && eventData) {
              currentContentBlocks = handleContentBlockEvent(
                eventData,
                streamingMsgId,
                currentContentBlocks
              );
              return;
            }

            handleToolEvents(status, eventData, streamingMsgId);

            if (status === 'error') {
              let errorText = '';
              try {
                if (eventData) {
                  const parsed = JSON.parse(eventData);
                  errorText = parsed?.error || parsed?.message || String(eventData);
                }
              } catch {
                errorText = eventData || 'Unknown error';
              }

              setExecutionStatus('error');

              const errorBlock = createTextBlock(`error_${Date.now()}`, errorText ? `Error: ${errorText}` : 'Unknown error', false);
              currentContentBlocks = [...currentContentBlocks, errorBlock];
              updateContentBlocksCallback(streamingMsgId, [...currentContentBlocks]);

              setMessages(prev => prev.map(m =>
                m.message_id === streamingMsgId
                  ? {
                    ...m,
                    isStreaming: false
                  }
                  : m
              ));
              return;
            }

            if (status === 'finished' || status === 'user_feedback') {
              setToolStepHistory(null);

              setExecutionStatus(status === 'finished' ? 'idle' : status);

              setMessages(prev => prev.map(m => {
                if (m.message_id === streamingMsgId) {
                  let updatedContent = m.content;

                  if (status === 'user_feedback' && Array.isArray(m.content)) {
                    updatedContent = m.content.map(block => {
                      if (block.type === 'tool_calls') {
                        const toolCallsData = block.data as any;
                        const hasOutput = toolCallsData.toolCalls?.some((tc: any) => tc.output);
                        if (!hasOutput) {
                          return { ...block, needsApproval: true };
                        }
                      } else if (block.type === 'plan') {
                        return { ...block, needsApproval: true };
                      }
                      return block;
                    });
                  }

                  const hasBlockNeedingApproval = Array.isArray(updatedContent)
                    ? updatedContent.some(block => block.needsApproval === true)
                    : false;

                  return {
                    ...m,
                    content: updatedContent,
                    isStreaming: false,
                    needsApproval: hasBlockNeedingApproval
                  };
                }
                return m;
              }));

              const streamingMessage = messagesRef.current.find(m => m.message_id === streamingMsgId);
              if (streamingMessage && Array.isArray(streamingMessage.content)) {
                const blockNeedingApproval = streamingMessage.content.find(block => block.needsApproval === true);
                if (blockNeedingApproval) {
                  setPendingApproval(blockNeedingApproval.id);
                }
              }
            }

            if (status === 'completed_payload') {
            }
            else if (status === 'visualizations_ready') {
            }


          });
        } catch (streamErr) {
          handleStreamingError(streamErr as Error, streamingMsgId);
        } finally {
          setStreamingActive(false);
        }
      } else {
        const messageText = handleResponse(response);
        const backendUuid = response.backendMessageId;
        const tempId = Date.now() + 1;
        const assistantMessage: MessageType = {
          message_id: backendUuid || String(tempId), // Store UUID from backend or use tempId as fallback
          sender: 'assistant',
          content: messageText ? [createTextBlock(`text_${tempId}`, messageText, false)] : [],
          timestamp: new Date(),
          threadId: contextThreadId || currentThreadId || undefined
        };
        setMessages(prev => [...prev, assistantMessage]);

        // Check if any block needs approval (block-level only)
        const hasBlockNeedingApproval = Array.isArray(assistantMessage.content) &&
          assistantMessage.content.some(block => block.needsApproval === true);
        if (hasBlockNeedingApproval) {
          setPendingApprovalFromMessage(assistantMessage);
        } else {
          setPendingApproval(null);
        }
      }

    } catch (error) {
      // Add error message
      const errorMessageId = Date.now() + 1;
      const errorMessage: MessageType = {
        message_id: String(errorMessageId),
        sender: 'assistant',
        content: [createTextBlock(`error_${errorMessageId}`, `Error: ${(error as Error).message || 'Something went wrong'}`, false)],
        timestamp: new Date()
      };

      setMessages(prev => [...prev, errorMessage]);
    }
  };

  const handleApprove = async (blockId: string): Promise<void> => {
    // Find the message containing this block
    const message = messages.find(m =>
      Array.isArray(m.content) && m.content.some(block => block.id === blockId)
    );

    if (!message) {
      console.warn('handleApprove: pending approval message not found', { blockId });
      return;
    }

    const block = Array.isArray(message.content) ? message.content.find(b => b.id === blockId) : null;
    if (!block || !block.needsApproval) {
      console.warn('handleApprove: block not found or no longer awaiting approval', { blockId, messageId: message.message_id });
      return;
    }

    setPendingApproval(null);
    setExecutionStatus('running');
    setIsLoading(true);

    try {
      if (Array.isArray(message.content)) {
        const updatedContent = message.content.map(b =>
          b.id === blockId
            ? { ...b, messageStatus: 'approved' as const, needsApproval: false }
            : b
        );
        await updateMessageFlags(message.message_id, {
          content: updatedContent
        });
      } else {
        await updateMessageFlags(message.message_id, {
          content: message.content
        });
      }
    } catch (updateError) {
      console.error('Failed to persist approval status:', updateError)
    }

    try {

      if (onApprove) {
        const textContent = Array.isArray(message.content)
          ? message.content
            .filter(block => block.type === 'text')
            .map(block => (block.data as any).text)
            .join('\n')
          : message.content;

        const latestAssistantMsgId = getLatestAssistantMessageId();
        const streamingMsgId = latestAssistantMsgId || message.message_id;
        const result = await onApprove(streamingMsgId, textContent, message);
        if (result) {
          if ((result as HandlerResponse).isStreaming && (result as HandlerResponse).streamingHandler) {

            const latestAssistantMsgId = getLatestAssistantMessageId();
            const streamingMsgId = latestAssistantMsgId || message.message_id;

            const existingMessageIndex = messages.findIndex(m => m.message_id === streamingMsgId);

            if (existingMessageIndex !== -1) {
              setMessages(prev => prev.map((m, idx) =>
                idx === existingMessageIndex
                  ? {
                    ...m,
                    isStreaming: true,
                    needsApproval: false
                  }
                  : m
              ));
            } else {
              const streamingMessage: MessageType = {
                message_id: streamingMsgId,
                sender: 'assistant',
                content: [],
                timestamp: new Date(),
                threadId: message.threadId || contextThreadId || currentThreadId || undefined,
                isStreaming: true
              } as any;
              setMessages(prev => [...prev, streamingMessage]);
            }

            setStreamingActive(true);
            setHasReceivedContent(false);

            if (message.message_id && typeof message.message_id === 'string') {
              backendToFrontendMessageIdMap.current.set(streamingMsgId, message.message_id);
            }
            try {

              const existingMessage = messages.find(m => m.message_id === streamingMsgId);
              let currentContentBlocks: ContentBlock[] = Array.isArray(existingMessage?.content)
                ? existingMessage.content.map(block => ({
                  ...block,
                  needsApproval: false
                }))
                : [];

              await (result as HandlerResponse).streamingHandler!(streamingMsgId, updateContentBlocksCallback, (status, eventData, responseType) => {
                if (!status) return;
                if (status === 'content_block' && eventData) {
                  currentContentBlocks = handleContentBlockEvent(
                    eventData,
                    streamingMsgId,
                    currentContentBlocks
                  );
                  return;
                }

                if (status === 'graph_node' && eventData) {
                  try {
                    const nodeData = JSON.parse(eventData);
                    if ((window as any).updateGraphNodeStatus) {
                      (window as any).updateGraphNodeStatus(
                        nodeData.node_id,
                        nodeData.status,
                        nodeData.previous_node_id
                      );
                    }
                  } catch (e) {
                    console.error("Failed to parse graph_node event", e);
                  }
                }

                if (status === 'tool_call' && eventData) {
                  const toolData = JSON.parse(eventData);
                  setToolStepHistory(prev => {
                    const newStep = {
                      name: toolData.tool_name || 'Unknown Tool',
                      id: toolData.tool_id,
                      startTime: Date.now(),
                      status: 'calling' as const
                    };
                    return {
                      messageId: streamingMsgId,
                      steps: [
                        ...(prev?.messageId === streamingMsgId ? prev.steps : []),
                        newStep
                      ]
                    };
                  });
                }

                // Handle error status from agent and append error message
                if (status === 'error') {
                  let errorText = '';
                  try {
                    if (eventData) {
                      const parsed = JSON.parse(eventData);
                      errorText = parsed?.error || parsed?.message || String(eventData);
                    }
                  } catch {
                    errorText = eventData || 'Unknown error';
                  }

                  // Update execution status to error
                  setExecutionStatus('error');

                  setMessages(prev => prev.map(m => {
                    if (m.message_id === streamingMsgId) {
                      const existingText = Array.isArray(m.content)
                        ? m.content.filter(b => b.type === 'text').map(b => (b.data as any).text).join('\n')
                        : '';
                      const errorBlock = createTextBlock(`error_${streamingMsgId}`, errorText ? `Error: ${errorText}` : 'Error occurred', false);
                      return {
                        ...m,
                        content: existingText ? [createTextBlock(`text_${streamingMsgId}`, existingText, false), errorBlock] : [errorBlock],
                        isStreaming: false
                      };
                    }
                    return m;
                  }));
                  return;
                }


                if (status === 'tool_result' && eventData) {
                  const resultData = JSON.parse(eventData);
                  setToolStepHistory(prev => {
                    if (!prev || prev.messageId !== streamingMsgId) return prev;

                    const updatedSteps = prev.steps.map(step =>
                      step.id === resultData.tool_call_id
                        ? { ...step, status: 'completed' as const, endTime: Date.now() }
                        : step
                    );
                    return { ...prev, steps: updatedSteps };
                  });
                }


                if (status === 'finished' || status === 'user_feedback') {
                  setToolStepHistory(null);

                  // Update execution status to match streaming status
                  setExecutionStatus(status === 'finished' ? 'idle' : status);

                  // If user_feedback, mark tool_calls blocks as needing approval
                  setMessages(prev => prev.map(m => {
                    if (m.message_id === streamingMsgId) {
                      let updatedContent = m.content;

                      // For user_feedback status, set needsApproval on tool_calls blocks
                      if (status === 'user_feedback' && Array.isArray(m.content)) {
                        updatedContent = m.content.map(block => {
                          // Set needsApproval=true on tool_calls blocks that don't have output yet
                          if (block.type === 'tool_calls') {
                            const toolCallsData = block.data as any;
                            const hasOutput = toolCallsData.toolCalls?.some((tc: any) => tc.output);
                            // Only set needsApproval if the tool doesn't have output yet
                            if (!hasOutput) {
                              return { ...block, needsApproval: true };
                            }
                          }
                          return block;
                        });
                      }

                      const hasBlockNeedingApproval = Array.isArray(updatedContent)
                        ? updatedContent.some(block => block.needsApproval === true)
                        : false;

                      return {
                        ...m,
                        content: updatedContent,
                        isStreaming: false,
                        needsApproval: hasBlockNeedingApproval
                      };
                    }
                    return m;
                  }));

                  // Set pending approval to the first block that needs approval
                  const streamingMessage = messagesRef.current.find(m => m.message_id === streamingMsgId);
                  if (streamingMessage && Array.isArray(streamingMessage.content)) {
                    // Find the first block that actually needs approval
                    const blockNeedingApproval = streamingMessage.content.find(block => block.needsApproval === true);
                    if (blockNeedingApproval) {
                      setPendingApproval(blockNeedingApproval.id);
                    }
                  }
                }
              });
            } catch (streamErr) {
              setMessages(prev => prev.map(m =>
                m.message_id === streamingMsgId
                  ? { ...m, content: [createTextBlock(`error_${streamingMsgId}`, `Error: ${(streamErr as Error).message || 'Streaming failed'}`, false)], isStreaming: false }
                  : m
              ));

            } finally {
              setStreamingActive(false);
            }
          } else {
            const messageText = handleResponse(result as HandlerResponse);
            const backendId = (result as HandlerResponse).backendMessageId || Date.now().toString();
            const needsApproval = (result as HandlerResponse).needsApproval || false;
            const tempId = Date.now() + 1;
            const resultMessage: MessageType = {
              message_id: backendId,
              sender: 'assistant',
              content: messageText ? [createTextBlock(`text_${tempId}`, messageText, false)] : [],
              timestamp: new Date(),
              threadId: contextThreadId || currentThreadId || undefined
            };
            setMessages(prev => [...prev, resultMessage]);
            // Note: Approval status was already persisted upfront, no need to update again
          }
        }
      }

    } catch (error) {
      const isTimeout = isTimeoutError(error as Error);

      if (isTimeout) {
        // Restore needsApproval if approval process timed out
        if (Array.isArray(message.content)) {
          const updatedContent = message.content.map(b =>
            b.id === blockId
              ? { ...b, messageStatus: 'timeout' as const, needsApproval: true }
              : b
          );
          await updateMessageFlags(message.message_id, {
            content: updatedContent
          });
        } else {
          // For legacy messages without content blocks, update content
          await updateMessageFlags(message.message_id, {
            content: message.content
          });
        }
      } else {
        // Restore needsApproval if approval process failed
        if (Array.isArray(message.content)) {
          const updatedContent = message.content.map(b =>
            b.id === blockId
              ? { ...b, messageStatus: 'pending' as const, needsApproval: true }
              : b
          );
          await updateMessageFlags(message.message_id, {
            content: updatedContent
          });
        } else {
          // For legacy messages without content blocks, update content
          await updateMessageFlags(message.message_id, {
            content: message.content
          });
        }

        const errorMessageId = String(Date.now() + 1);
        const errorMessage: MessageType = {
          message_id: errorMessageId,
          sender: 'assistant',
          content: [createTextBlock(`error_${errorMessageId}`, `Error during approval: ${(error as Error).message || 'Something went wrong'}`, false)],
          timestamp: new Date()
        };

        setMessages(prev => [...prev, errorMessage]);
      }
    }
    finally {
      setIsLoading(false);
    }
  };


  const handleCancel = async (blockId: string): Promise<void> => {
    // Find the message containing this block
    const message = messages.find(m =>
      Array.isArray(m.content) && m.content.some(block => block.id === blockId)
    );

    if (!message) {
      return;
    }

    const block = Array.isArray(message.content) ? message.content.find(b => b.id === blockId) : null;
    if (!block || !block.needsApproval) {
      return;
    }

    setPendingApproval(null);
    setExecutionStatus('running');
    setIsLoading(true);

    // Update the specific block to show it's cancelled
    if (Array.isArray(message.content)) {
      const updatedContent = message.content.map(b =>
        b.id === blockId
          ? { ...b, messageStatus: 'rejected' as const, needsApproval: false }
          : b
      );

      // Check if message still needs approval after updating this block
      const stillNeedsApproval = updatedContent.some(b => b.needsApproval === true);

      await updateMessageFlags(message.message_id, {
        content: updatedContent
      });
    } else {
      // For legacy messages without content blocks, update content
      await updateMessageFlags(message.message_id, {
        content: message.content
      });
    }

    try {
      // Use onFeedback for rejection instead of onCancel
      if (onFeedback) {
        const result = await onFeedback(message.message_id, "Rejected", message);

        // If the feedback handler returns a result, add it as a new message
        if (result) {
          const resultMessageId = String(Date.now() + 1);
          const resultText = typeof result === 'string' ? result : (result as HandlerResponse).message || '';
          const resultMessage: MessageType = {
            message_id: resultMessageId,
            sender: 'assistant',
            content: resultText ? [createTextBlock(`text_${resultMessageId}`, resultText, false)] : [],
            timestamp: new Date()
          };

          setMessages(prev => [...prev, resultMessage]);
        }
      }
    } catch (error) {
      // Add error message if rejection fails
      const errorMessageId = String(Date.now() + 1);
      const errorMessage: MessageType = {
        message_id: errorMessageId,
        sender: 'assistant',
        content: [createTextBlock(`text_${errorMessageId}`, `Error during rejection: ${(error as Error).message || 'Something went wrong'}`, false)],
        timestamp: new Date()
      };

      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopStream = () => {
    console.log('Stopping stream...');
    setStreamingActive(false);
    setIsLoading(false);
    setExecutionStatus('idle');

    // Note: EventSource closing is handled in page.tsx
    // This handler just updates the local UI state
  };

  const handleRetry = async (messageId: string): Promise<void> => {
    const message = messages.find(m => m.message_id === messageId);
    // Check if message has timeout status in any block (can be retried)
    const hasTimeoutBlock = message && Array.isArray(message.content) &&
      message.content.some(block => block.messageStatus === 'timeout');
    if (!message || !hasTimeoutBlock) {
      return;
    }

    // Clear the timeout state on blocks and restore to pending status
    if (Array.isArray(message.content)) {
      const updatedContent = message.content.map(block =>
        block.messageStatus === 'timeout'
          ? { ...block, messageStatus: 'pending' as const }
          : block
      );
      await updateMessageFlags(messageId, {
        content: updatedContent
      });
    }

    try {
      // Call the parent's retry handler if available
      if (onRetry) {
        const result = await onRetry(message);

        // If the retry handler returns a result, add it as a new message
        if (result) {
          // Handle response (could be string or HandlerResponse)
          const messageText = handleResponse(result);
          const resultMessageId = (Date.now() + 1).toString();

          const resultMessage: MessageType = {
            message_id: resultMessageId,
            sender: 'assistant',
            content: messageText ? [createTextBlock(`text_${resultMessageId}`, messageText, false)] : [],
            timestamp: new Date(),
            threadId: contextThreadId || currentThreadId || undefined
          };

          setMessages(prev => [...prev, resultMessage]);
        }
      } else {
        // Fallback to local retry logic if no parent handler
        // For timeout retries, find the first block that needs approval and approve it
        const hasApprovalNeeded = Array.isArray(message.content) &&
          message.content.some(block => block.needsApproval === true);
        if (hasApprovalNeeded && Array.isArray(message.content)) {
          const blockNeedingApproval = message.content.find(block => block.needsApproval === true);
          if (blockNeedingApproval) {
            await handleApprove(blockNeedingApproval.id);
          }
        }
      }
    } catch (error) {
      const isTimeout = isTimeoutError(error as Error);

      // If retry fails, mark blocks as having a timeout error again
      if (Array.isArray(message.content)) {
        const updatedContent = message.content.map(block =>
          block.messageStatus === 'pending'
            ? { ...block, messageStatus: 'timeout' as const }
            : block
        );
        await updateMessageFlags(messageId, {
          content: updatedContent
        });
      }
      console.error('Retry failed:', error);

      // Also show the error message if it's not a timeout
      if (!isTimeout) {
        const errorMessageId = (Date.now() + 1).toString();
        const errorMessage: MessageType = {
          message_id: errorMessageId,
          sender: 'assistant',
          content: [createTextBlock(`error_${errorMessageId}`, `Retry failed: ${(error as Error).message || 'Something went wrong'}`, false)],
          timestamp: new Date()
        };
        setMessages(prev => [...prev, errorMessage]);
      }
    } finally {
      setIsLoading(false);
    }
    // Note: Loading state cleanup is handled by the parent component
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Enhanced input handlers
  const handleFilesChange = (files: File[]): void => {
    setAttachedFiles(files);
  };

  const handlePlanningToggle = (enabled: boolean): void => {
    setUsePlanning(enabled);
  };

  const handleExplainerToggle = (enabled: boolean): void => {
    setUseExplainer(enabled);
  };

  const handleStreamingToggle = (enabled: boolean): void => {
    setUseStreaming(enabled);
  };

  return (
    <ResizablePanelGroup
      key={graphPanelOpen ? 'split' : 'full'}
      orientation="horizontal"
      className={`h-full ${className}`}
    >
      {/* Chat Panel */}
      <ResizablePanel defaultSize={graphPanelOpen ? 60 : 100} minSize={5}>
        <div
          className={`relative flex flex-col h-full min-h-0 ${messages.length === 0 && !currentThreadId ? 'justify-end md:justify-center md:pb-32' : ''}`}
        >
          {/* Thread Title - responsive background */}
          {threadTitle && (
            <>
              {/* Mobile: Full-width background with gradient bottom */}
              <div className={`md:hidden absolute top-0 left-0 right-0 z-30 transition-[left] duration-300 ease-in-out`}>
                {/* Main background */}
                <div className="bg-background py-3 pr-4 pl-14">
                  <ThreadTitle
                    title={threadTitle}
                    threadId={currentThreadId || undefined}
                    onTitleChange={onTitleChange}
                  />
                </div>
                {/* Very sharp gradient fade at bottom */}
                <div className="h-3 bg-gradient-to-b from-background via-background/20 to-transparent"></div>
              </div>

              {/* Desktop: Background with gradient bottom */}
              <div className={`hidden md:block absolute top-0 left-0 right-0 z-30 transition-[left] duration-300 ease-in-out`}>
                {/* Main background */}
                <div className={`bg-background py-3 pr-4 pl-4 transition-[padding-left] duration-300 ease-in-out`}>
                  <ThreadTitle
                    title={threadTitle}
                    threadId={currentThreadId || undefined}
                    onTitleChange={onTitleChange}
                  />
                </div>
                {/* Very sharp gradient fade at bottom */}
                <div className="h-3 bg-gradient-to-b from-background via-background/20 to-transparent"></div>
              </div>
            </>
          )}

          {/* Messages - scrollable area with padding for fixed input and header */}
          <div
            ref={messagesContainerRef}
            className={`relative space-y-4 min-h-0 slim-scroll pb-40 overflow-y-auto ${messages.length === 0 && !currentThreadId ? '' : 'flex-1'} ${threadTitle ? 'pt-38' : 'pt-8'}`}
          >
            <div className="max-w-3xl mx-auto px-4">
              {messages.map((message) => (
                <React.Fragment key={message.message_id}>
                  <Message
                    message={message}
                    onRetry={handleRetry}
                    onApproveBlock={handleApprove}
                    onRejectBlock={handleCancel}
                  />

                  {(() => {
                    const shouldShow = message.isStreaming &&
                      toolStepHistory?.messageId === message.message_id &&
                      toolStepHistory.steps.length > 0;
                    return shouldShow && (
                      <EphemeralToolIndicator steps={toolStepHistory.steps} />
                    );
                  })()}
                </React.Fragment>
              ))}

              {/* Loading indicator - shows when waiting for content */}
              {(isLoading || (useStreaming && streamingActive && !hasReceivedContent)) && (
                <GeneratingIndicator
                  activeTools={toolStepHistory?.steps.filter(s => s.status === 'calling').map(s => s.name)}
                />
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Scroll to bottom button - fixed above input form, aligned with messages */}
            {!isAtBottom && messages.length > 0 && (
              <div className={`absolute left-0 right-0 bottom-42 z-30 pointer-events-none px-4`}>
                <div className="max-w-3xl px-4 mx-auto">
                  <div className="flex justify-end">
                    <button
                      onClick={() => scrollToBottom()}
                      className="pointer-events-auto w-10 h-10 rounded-full bg-muted border-1 border-foreground/20 shadow-lg hover:bg-accent hover:border-foreground/30 hover:shadow-xl transition-all duration-200 flex items-center justify-center group"
                      title="Scroll to bottom"
                      aria-label="Scroll to bottom"
                    >
                      <ChevronDown className="w-5 h-5 text-foreground group-hover:text-foreground" />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className={`z-10 transition-all duration-300 ease-in-out bg-background/80 backdrop-blur-sm ${messages.length === 0 && !currentThreadId
            ? 'w-full flex justify-center pb-3'
            : 'absolute left-0 right-0 bottom-0 pb-3'
            }`}>

            <div className={`${messages.length === 0 && !currentThreadId ? 'max-w-4xl px-6' : 'max-w-3xl px-4'} min-w-[320px] w-full mx-auto`}>
              {messages.length === 0 && !currentThreadId && (
                <div className="hidden md:block mb-5 text-center text-muted-foreground">
                  <span className="text-3xl">Hi User! Start a conversation</span>
                </div>
              )}
              <InputForm
                value={inputValue}
                onChange={setInputValue}
                onSend={handleSend}
                onKeyDown={handleKeyDown}
                placeholder={pendingApproval ? "Your feedback..." : placeholder}
                disabled={disabled}
                isLoading={isLoading}
                usePlanning={usePlanning}
                useExplainer={useExplainer}
                useStreaming={useStreaming}
                onPlanningToggle={handlePlanningToggle}
                onExplainerToggle={handleExplainerToggle}
                onStreamingToggle={handleStreamingToggle}
                onFilesChange={handleFilesChange}
                attachedFiles={attachedFiles}
                hasDataContext={hasDataContext}
                onOpenDataContext={onOpenDataContext}
                isStreaming={streamingActive}
                onStopStream={handleStopStream}
                onToggleGraphPanel={onToggleGraphPanel}
              />
            </div>
          </div>
        </div>
      </ResizablePanel>

      {/* Resizable Handle - only show when graph panel is open */}
      {graphPanelOpen && (
        <ResizableHandle withHandle className="w-1.5 hover:w-2 hover:bg-primary/50 transition-all cursor-col-resize" />
      )}

      {/* Graph Panel - only render when open */}
      {graphPanelOpen && (
        <ResizablePanel defaultSize={40} minSize={5}>
          <GraphFlowPanel
            open={true}
            onClose={() => onToggleGraphPanel?.()}
            threadId={currentThreadId || undefined}
            graphStructure={graphStructure}
          />
        </ResizablePanel>
      )}
    </ResizablePanelGroup>
  );
};

export default ChatComponent;