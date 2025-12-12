'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Message, HandlerResponse } from '@/types/chat';
import { ConversationService, GraphService, ExplorerService, VisualizationService, DataService } from '@/services';
import type { DataFramePreviewData, MessageStatus, GraphResponse } from '@/types';
import { ApprovalStatus } from '@/types';
import ChatComponent from '@/components/chat/ChatComponent';
import Sidebar from '@/components/sidebar/Sidebar';
import ExecutionHistory from '@/components/ExecutionHistory';
import ExplorerPanel from '@/components/panels/ExplorerPanel';
import VisualizationPanel from '@/components/panels/VisualizationPanel';
import DataFramePanel from '@/components/panels/DataFramePanel';

const ChatWithApproval: React.FC = () => {
  // Local state management (replacing UIStateContext)
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [executionStatus, setExecutionStatus] = useState<'running' | 'user_feedback' | 'finished' | 'error'>('finished');
  const [loading, setLoading] = useState(false);
  const [useStreaming] = useState(true); // Default to streaming

  const [selectedChatThreadId, setSelectedChatThreadId] = useState<string | null>(null);
  const [restoredMessages, setRestoredMessages] = useState<Message[]>([]);
  const [currentThreadTitle, setCurrentThreadTitle] = useState<string>('');
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [chatKey, setChatKey] = useState(0);
  const [showExecutionHistory, setShowExecutionHistory] = useState(false);
  const [loadingThread, setLoadingThread] = useState(false);

  // Panel states
  const [explorerOpen, setExplorerOpen] = useState(false);
  const [explorerData, setExplorerData] = useState<any>(null);
  const [visualizationOpen, setVisualizationOpen] = useState(false);
  const [visualizationCharts, setVisualizationCharts] = useState<any>(null);
  const [dataFrameOpen, setDataFrameOpen] = useState(false);
  const [dataFrameData, setDataFrameData] = useState<DataFramePreviewData | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const currentThreadIdRef = useRef<string | null>(null);

  // Thread ID reference to handle race conditions
  useEffect(() => {
    // Observe context value updates
  }, [useStreaming]);

  const convertChatHistoryToMessages = (chatMessages: any[]): Message[] => {
    return chatMessages.map((msg, index) => {
      // Content is always an array from backend
      let content: any[] = [];
      const normalizeBlock = (block: any, blockIndex: number) => ({
        ...block,
        id: block.id || block.block_id || `block_${msg.message_id || index}_${blockIndex}`,
        needsApproval: block.needsApproval ?? block.needs_approval ?? false,
        messageStatus: block.messageStatus ?? block.message_status
      });

      if (Array.isArray(msg.content)) {
        content = msg.content.map(normalizeBlock);
      } else if (msg.content_blocks && Array.isArray(msg.content_blocks)) {
        // Backward compatibility: if content_blocks exists, use it
        content = msg.content_blocks.map(normalizeBlock);
      } else if (typeof msg.content === 'string' && msg.content.trim().length > 0) {
        // Legacy: convert string content to text block
        content = [{
          id: `text_${(typeof msg.message_id === 'number' ? msg.message_id : Date.now())}`,
          type: 'text',
          needsApproval: false,
          data: { text: msg.content }
        }];
      }

      // Determine needsApproval and messageStatus from content blocks
      let needsApproval = false;
      let messageStatus: 'pending' | 'approved' | 'rejected' | 'error' | 'timeout' | undefined = undefined;

      if (Array.isArray(content) && content.length > 0) {
        // Check if any block needs approval
        needsApproval = content.some((block: any) => block.needsApproval === true || block.needs_approval === true);

        // Get messageStatus from blocks (use the first non-null status found)
        for (const block of content) {
          if (block.messageStatus || block.message_status) {
            messageStatus = block.messageStatus || block.message_status;
            break;
          }
        }

        // If no block has messageStatus but needsApproval is true, set to pending
        if (!messageStatus && needsApproval) {
          messageStatus = 'pending';
        }
      } else if (msg.message_status) {
        // Fallback to message-level status (legacy)
        messageStatus = msg.message_status;
        needsApproval = messageStatus === 'pending';
      }

      return {
        id: (typeof msg.message_id === 'number' ? msg.message_id : (Date.now() + index)),
        role: (msg.sender === 'assistant' ? 'assistant' : 'user'),
        content,
        timestamp: new Date(msg.timestamp),
        needsApproval,
        messageStatus,
        threadId: msg.thread_id || selectedChatThreadId || undefined,
        checkpointId: msg.checkpoint_id
      } as Message;
    });
  };

  const restoreDataIfNeeded = async (messages: Message[], threadId: string) => {
    // Find messages with explorer blocks (new content blocks structure)
    const explorerBlocksInfo: Array<{ messageId: number, blockId: string, checkpointId: string }> = [];
    const visualizationBlocksInfo: Array<{ messageId: number, blockId: string, checkpointId: string }> = [];

    // Also check for legacy format
    const legacyExplorerMessages = messages.filter(msg =>
      msg.messageType === 'explorer' &&
      msg.checkpointId &&
      msg.role === 'assistant'
    );

    const legacyVisualizationMessages = messages.filter(msg =>
      msg.messageType === 'visualization' &&
      msg.role === 'assistant'
    );

    // Extract explorer and visualization blocks from content blocks
    messages.forEach(msg => {
      if (Array.isArray(msg.content)) {
        msg.content.forEach(block => {
          if (block.type === 'explorer') {
            const explorerData = block.data as any;
            if (explorerData.checkpointId) {
              explorerBlocksInfo.push({
                messageId: msg.id,
                blockId: block.id,
                checkpointId: explorerData.checkpointId
              });
            }
          } else if (block.type === 'visualizations') {
            const visualizationData = block.data as any;
            if (visualizationData.checkpointId) {
              visualizationBlocksInfo.push({
                messageId: msg.id,
                blockId: block.id,
                checkpointId: visualizationData.checkpointId
              });
            }
          }
        });
      }
    });

    const hasExplorerData = explorerBlocksInfo.length > 0 || legacyExplorerMessages.length > 0;
    const hasVisualizationData = visualizationBlocksInfo.length > 0 || legacyVisualizationMessages.length > 0;

    if (hasExplorerData || hasVisualizationData) {
      try {
        const explorerDataMap = new Map();
        const visualizationDataMap = new Map();

        // Restore explorer data from content blocks
        for (const blockInfo of explorerBlocksInfo) {
          try {
            const explorerResponse = await ExplorerService.getExplorerData(
              threadId,
              blockInfo.checkpointId
            );

            if (explorerResponse?.data) {
              explorerDataMap.set(`${blockInfo.messageId}_${blockInfo.blockId}`, explorerResponse.data);
            }
          } catch (error) {
            console.error('Failed to restore explorer data for checkpoint:', blockInfo.checkpointId, error);
          }
        }

        // Restore legacy explorer data
        for (const explorerMessage of legacyExplorerMessages) {
          try {
            const explorerResponse = await ExplorerService.getExplorerData(
              threadId,
              explorerMessage.checkpointId!
            );

            if (explorerResponse?.data) {
              explorerDataMap.set(`legacy_${explorerMessage.id}`, explorerResponse.data);
            }
          } catch (error) {
            console.error('Failed to restore legacy explorer data for checkpoint:', explorerMessage.checkpointId, error);
          }
        }

        // Restore visualization data from content blocks
        for (const blockInfo of visualizationBlocksInfo) {
          try {
            const visualizationResponse = await VisualizationService.getVisualizationData(
              threadId,
              blockInfo.checkpointId
            );
            if (visualizationResponse?.data?.visualizations) {
              visualizationDataMap.set(`${blockInfo.messageId}_${blockInfo.blockId}`, visualizationResponse.data.visualizations);
            }
          } catch (error) {
            console.error('Failed to restore visualization data for checkpoint:', blockInfo.checkpointId, error);
          }
        }

        // Restore legacy visualization data
        for (const visualizationMessage of legacyVisualizationMessages) {
          try {
            const visualizationResponse = await VisualizationService.getVisualizationData(
              threadId,
              visualizationMessage.checkpointId || ''
            );
            if (visualizationResponse?.data?.visualizations) {
              visualizationDataMap.set(`legacy_${visualizationMessage.id}`, visualizationResponse.data.visualizations);
            }
          } catch (error) {
            console.error('Failed to restore legacy visualization data for checkpoint:', visualizationMessage.checkpointId, error);
          }
        }

        // Update messages with restored data
        const updatedMessages = messages.map(msg => {
          let updatedMsg = { ...msg };

          // Handle content blocks structure
          if (Array.isArray(msg.content)) {
            const updatedContentBlocks = msg.content.map(block => {
              if (block.type === 'explorer') {
                const explorerDataKey = `${msg.id}_${block.id}`;
                const explorerData = explorerDataMap.get(explorerDataKey);
                if (explorerData) {
                  return {
                    ...block,
                    data: {
                      ...block.data,
                      explorerData
                    }
                  };
                }
              } else if (block.type === 'visualizations') {
                const visualizationDataKey = `${msg.id}_${block.id}`;
                const visualizations = visualizationDataMap.get(visualizationDataKey);
                if (visualizations) {
                  return {
                    ...block,
                    data: {
                      ...block.data,
                      visualizations
                    }
                  };
                }
              }
              return block;
            });

            updatedMsg = {
              ...updatedMsg,
              content: updatedContentBlocks
            };
          }

          // Handle legacy format
          if (msg.messageType === 'explorer' && explorerDataMap.has(`legacy_${msg.id}`)) {
            const explorerData = explorerDataMap.get(`legacy_${msg.id}`);
            updatedMsg = {
              ...updatedMsg,
              metadata: {
                ...updatedMsg.metadata,
                explorerData
              }
            };
          }

          if (msg.messageType === 'visualization' && visualizationDataMap.has(`legacy_${msg.id}`)) {
            const visualizations = visualizationDataMap.get(`legacy_${msg.id}`);
            updatedMsg = {
              ...updatedMsg,
              metadata: {
                ...updatedMsg.metadata,
                visualizations: visualizations
              }
            };
          }

          return updatedMsg;
        });

        setRestoredMessages(updatedMessages);

        // If any restored message needs approval, set execution status to user_feedback
        if (updatedMessages.some(m => m.needsApproval)) {
          setExecutionStatus('user_feedback');
        }

        // Set the latest explorer data (prioritize content blocks over legacy)
        let latestExplorerData = null;
        if (explorerBlocksInfo.length > 0) {
          const lastBlockInfo = explorerBlocksInfo[explorerBlocksInfo.length - 1];
          latestExplorerData = explorerDataMap.get(`${lastBlockInfo.messageId}_${lastBlockInfo.blockId}`);
        } else if (legacyExplorerMessages.length > 0) {
          const lastExplorerMessage = legacyExplorerMessages[legacyExplorerMessages.length - 1];
          latestExplorerData = explorerDataMap.get(`legacy_${lastExplorerMessage.id}`);
        }

        if (latestExplorerData) {
          setExplorerData(latestExplorerData);
        }

        // Set the latest visualization data (prioritize content blocks over legacy)
        let latestVisualizationData = null;
        if (visualizationBlocksInfo.length > 0) {
          const lastBlockInfo = visualizationBlocksInfo[visualizationBlocksInfo.length - 1];
          latestVisualizationData = visualizationDataMap.get(`${lastBlockInfo.messageId}_${lastBlockInfo.blockId}`);
        } else if (legacyVisualizationMessages.length > 0) {
          const lastVisualizationMessage = legacyVisualizationMessages[legacyVisualizationMessages.length - 1];
          latestVisualizationData = visualizationDataMap.get(`legacy_${lastVisualizationMessage.id}`);
        }

        if (latestVisualizationData) {
          setVisualizationCharts(latestVisualizationData);
        }

      } catch (error) {
        console.error('Failed to restore data:', error);
      }
    } else {
      setRestoredMessages(messages);
      // If any restored message needs approval, set execution status to user_feedback
      if (messages.some(m => m.needsApproval)) {
        setExecutionStatus('user_feedback');
      }
    }
  };

  const handleOpenExplorer = async (data: any) => {
    if (data) {
      // Ensure only one panel is open at a time
      setVisualizationOpen(false);
      setVisualizationCharts(null);
      setDataFrameOpen(false);
      setDataFrameData(null);

      // Check if explorerData is already loaded
      let explorerData = data.data;

      // Determine checkpointId - could be in data.checkpointId or data.data.checkpointId
      const checkpointId = data.checkpointId || (data.data && data.data.checkpointId);

      // Check if explorerData is valid (has steps or checkpoint_id, indicating it's full explorer data)
      const hasValidExplorerData = explorerData &&
        typeof explorerData === 'object' &&
        (explorerData.steps || explorerData.checkpoint_id || explorerData.overall_confidence !== undefined);

      // If explorerData is not valid or missing, fetch it from API
      if (!hasValidExplorerData && checkpointId) {
        // Get threadId from context (same pattern as handleMessageUpdated)
        const threadId = currentThreadIdRef.current || currentThreadId || selectedChatThreadId;
        if (threadId) {
          try {
            // Fetch explorer data using the same pattern as handleCheckpointClick
            const explorerResponse = await ExplorerService.getExplorerData(threadId, checkpointId);
            explorerData = explorerResponse?.data;
          } catch (error) {
            console.error('Error fetching explorer data for checkpoint:', checkpointId, error);
            // Continue with whatever data we have (might be empty)
            explorerData = explorerData || null;
          }
        } else {
          console.warn('No threadId available to fetch explorer data');
          explorerData = explorerData || null;
        }
      } else if (!hasValidExplorerData) {
        // No checkpointId available, use whatever data we have
        explorerData = explorerData || null;
      }

      setExplorerData(explorerData);
      setExplorerOpen(true);
    }
  };

  const handleMessageUpdated = async (msg: Message) => {
    // Handle persistent storage of block-level approval updates
    const threadId = currentThreadIdRef.current || currentThreadId || selectedChatThreadId || msg.threadId;
    if (!threadId) {
      console.error('No thread ID available for message update');
      return;
    }

    try {
      // Update blocks individually if message has content blocks
      if (Array.isArray(msg.content)) {
        // Update each block that has status changes
        for (const block of msg.content) {
          // Only update blocks that have status-related fields
          if (block.needsApproval !== undefined || block.messageStatus !== undefined) {
            const blockUpdates: {
              needsApproval?: boolean;
              messageStatus?: MessageStatus;
            } = {};

            if (block.needsApproval !== undefined) {
              blockUpdates.needsApproval = block.needsApproval;
            }
            if (block.messageStatus !== undefined) {
              blockUpdates.messageStatus = block.messageStatus as MessageStatus;
            }

            // Only call API if there are actual updates
            if (Object.keys(blockUpdates).length > 0) {
              try {
                // Use message_id (UUID) instead of id (numeric timestamp)
                const messageId = msg.message_id || String(msg.id); // Fallback to string id if UUID not available
                await ConversationService.updateBlockApproval(threadId, messageId, block.id, blockUpdates);
              } catch (blockError) {
                console.error(`Failed to update block ${block.id} flags:`, blockError);
              }
            }
          }
        }
      } else {
        // Fallback: if message doesn't have content blocks, use legacy message-level update
        // This handles backward compatibility with old messages
        const legacyFields: any = {
          message_id: msg.id,
          needs_approval: msg.needsApproval
        };

        if (msg.messageStatus === 'error') {
          legacyFields.is_error = true;
        } else if (msg.messageStatus === 'timeout') {
          legacyFields.has_timed_out = true;
        }

        const messageId = msg.message_id || String(msg.id); // Use UUID or fallback to string id
        await ConversationService.updateMessageStatus(threadId, messageId, legacyFields);
      }

    } catch (error) {
      console.error('Failed to update message flags in database:', error);
    }
  };

  useEffect(() => {
    (window as any).openExplorer = handleOpenExplorer;
    (window as any).openVisualization = async (data: any) => {
      // Handle both direct charts array and wrapped data structure
      let charts = Array.isArray(data) ? data : (data?.charts || []);

      // If charts array is empty or missing, fetch it from API
      if (!charts || charts.length === 0) {
        const checkpointId = data?.checkpointId;

        if (checkpointId) {
          // Get threadId from context
          const threadId = currentThreadIdRef.current || currentThreadId || selectedChatThreadId;

          if (threadId) {
            try {
              // Fetch visualization data from API
              const visualizationResponse = await VisualizationService.getVisualizationData(threadId, checkpointId);

              // Fix: visualizations are at response.data.visualizations, not response.data.data
              if (visualizationResponse?.data?.visualizations) {
                charts = visualizationResponse.data.visualizations;
              }
            } catch (error) {
              console.error('Error fetching visualization data for checkpoint:', checkpointId, error);
              // Continue with empty charts array
            }
          } else {
            console.warn('No threadId available to fetch visualization data');
          }
        }
      }

      // Only open panel if we have charts
      if (charts && charts.length > 0) {
        setExplorerOpen(false);
        setExplorerData(null);
        setDataFrameOpen(false);
        setDataFrameData(null);
        setVisualizationCharts(charts);
        setVisualizationOpen(true);
      }
    };
    return () => {
      delete (window as any).openExplorer;
      delete (window as any).openVisualization;
    };
  }, [handleOpenExplorer, currentThreadId, selectedChatThreadId]);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const createNewChatThread = async (initialMessage?: string): Promise<string> => {
    try {
      const thread = await ConversationService.createConversation({
        title: initialMessage || 'New Chat',
        initial_message: initialMessage
      });
      return thread.data?.thread_id || '';
    } catch (error) {
      console.error('Error creating chat thread:', error);
      throw error;
    }
  };

  // Enhanced streaming message handler
  const startStreamingForMessage = async (
    messageContent: string,
    streamingMessageId: number,
    chatThreadId: string,
    updateContentCallback: (id: number, contentBlocks: any[]) => void,
    onStatus?: (status: 'user_feedback' | 'finished' | 'running' | 'error' | 'tool_call' | 'tool_result' | 'completed_payload' | 'visualizations_ready' | 'content_block', eventData?: string, responseType?: 'answer' | 'replan' | 'cancel') => void,
    usePlanning: boolean = true,
    useExplainer: boolean = true,
    preStartResponse?: GraphResponse
  ): Promise<void> => {
    try {
      const startResponse = preStartResponse ?? await GraphService.startStreamingGraph({
        human_request: messageContent,
        thread_id: chatThreadId,
        use_planning: usePlanning,
        use_explainer: useExplainer
      });

      setCurrentThreadId(startResponse.data?.thread_id || '');
      eventSourceRef.current = GraphService.streamResponse(
        startResponse.data?.thread_id || '',
        {
          onMessage: (data) => {
            if (data.content) {
              // Convert string content to content blocks for compatibility (legacy support)
              const contentBlocks = [{
                id: `text_${Date.now()}`,
                type: 'text',
                needsApproval: false,
                data: { text: data.content }
              }];
              updateContentCallback(streamingMessageId, contentBlocks);
            } else if (data.status === 'content_block') {
              // Handle new structured content blocks
              if (onStatus) {
                onStatus('content_block', data.eventData);
              }
            } else if (data.status) {
              if (data.status === 'completed_payload') {
                // Handle explorer data from completed payload
                const graphData = data.graph;
                if (graphData && graphData.steps && graphData.steps.length > 0) {
                  const explorerMessageId = Date.now() + Math.floor(Math.random() * 1000);
                  const explorerMessage = {
                    id: explorerMessageId,
                    role: 'assistant',
                    content: 'Explorer data available',
                    timestamp: new Date(),
                    messageType: 'explorer',
                    checkpointId: graphData.checkpoint_id,
                    metadata: { explorerData: graphData },
                    threadId: chatThreadId
                  };
                  if (updateContentCallback) {
                    const contentBlocks = [{
                      id: `text_${Date.now()}`,
                      type: 'text',
                      needsApproval: false,
                      data: { text: JSON.stringify(explorerMessage) }
                    }];
                    updateContentCallback(explorerMessageId, contentBlocks);
                  }
                }
              } else if (data.status === 'visualizations_ready') {
                // Handle visualization data
                const visualizations = data.visualizations || [];
                if (visualizations.length > 0) {
                  // Create a new message with its own ID for visualization data
                  const vizMessageId = Date.now() + Math.floor(Math.random() * 1000) + 10000;
                  const vizMessage = {
                    id: vizMessageId,
                    role: 'assistant',
                    content: 'Visualizations available',
                    timestamp: new Date(),
                    messageType: 'visualization',
                    checkpointId: data.checkpoint_id,
                    metadata: { visualizations: visualizations },
                    threadId: chatThreadId
                  };

                  if (updateContentCallback) {
                    const contentBlocks = [{
                      id: `text_${Date.now()}`,
                      type: 'text',
                      needsApproval: false,
                      data: { text: JSON.stringify(vizMessage) }
                    }];
                    updateContentCallback(vizMessageId, contentBlocks);
                  }
                }

              }
              else {
                setExecutionStatus(data.status);
              }

              if (onStatus) {
                onStatus(data.status, data.eventData, data.response_type);  // Pass eventData and response_type
              }
            }
          },
          onError: (error) => {
            console.error('Streaming error:', error);
            setLoading(false);
            throw error;
          },
          onComplete: () => {
            setLoading(false);
          }
        }
      );

    } catch (error) {
      console.error('Failed to start streaming:', error);
      setLoading(false);
      throw error;
    }
  };

  const resumeStreamingForMessage = async (
    threadId: string,
    reviewAction: ApprovalStatus,
    humanComment?: string,
    streamingMessageId?: number,
    updateContentCallback?: (id: number, contentBlocks: any[]) => void,
    onStatus?: (status: 'user_feedback' | 'finished' | 'running' | 'error' | 'tool_call' | 'tool_result' | 'completed_payload' | 'visualizations_ready' | 'content_block', eventData?: string, responseType?: 'answer' | 'replan' | 'cancel') => void,
    preResumeResponse?: GraphResponse
  ): Promise<void> => {
    try {
      const resumeResponse = preResumeResponse ?? await GraphService.resumeStreamingGraph({
        thread_id: threadId,
        review_action: reviewAction,
        human_comment: humanComment
      });


      eventSourceRef.current = GraphService.streamResponse(
        resumeResponse.data?.thread_id || threadId,
        {
          onMessage: (data) => {
            if (data.content && streamingMessageId && updateContentCallback) {
              // Convert string content to content blocks for compatibility (legacy support)
              const contentBlocks = [{
                id: `text_${Date.now()}`,
                type: 'text',
                needsApproval: false,
                data: { text: data.content }
              }];
              updateContentCallback(streamingMessageId, contentBlocks);
            } else if (data.status === 'content_block') {
              // Handle new structured content blocks
              if (onStatus) {
                onStatus('content_block', data.eventData);
              }
            } else if (data.status) {
              if (data.status === 'completed_payload') {
                // Handle explorer data from completed payload
                const graphData = data.graph;
                if (graphData && graphData.steps && graphData.steps.length > 0) {
                  // Create a new message with its own ID for explorer data
                  const explorerMessageId = Date.now() + Math.floor(Math.random() * 1000);
                  const explorerMessage = {
                    id: explorerMessageId,
                    role: 'assistant',
                    content: 'Explorer data available',
                    timestamp: new Date(),
                    messageType: 'explorer',
                    checkpointId: graphData.checkpoint_id,
                    metadata: { explorerData: graphData },
                    threadId: threadId
                  };

                  // Add the explorer message to the chat using updateContentCallback with the new ID
                  if (updateContentCallback) {
                    const contentBlocks = [{
                      id: `text_${Date.now()}`,
                      type: 'text',
                      needsApproval: false,
                      data: { text: JSON.stringify(explorerMessage) }
                    }];
                    updateContentCallback(explorerMessageId, contentBlocks);
                  }

                  // Use the global window functions to open explorer
                  if ((window as any).openExplorer) {
                    (window as any).openExplorer(graphData);
                  }
                }
                // Don't append graph data to the streaming message content
                // The graph data is handled separately above for explorer messages
              } else if (data.status === 'visualizations_ready') {
                // Handle visualization data
                const visualizations = data.visualizations || [];
                if (visualizations.length > 0) {
                  // Create a new message with its own ID for visualization data
                  const vizMessageId = Date.now() + Math.floor(Math.random() * 1000) + 10000;
                  const vizMessage = {
                    id: vizMessageId,
                    role: 'assistant',
                    content: 'Visualizations available',
                    timestamp: new Date(),
                    messageType: 'visualization',
                    checkpointId: data.checkpoint_id,
                    metadata: { visualizations: visualizations },
                    threadId: threadId
                  };

                  // Add the visualization message to the chat using updateContentCallback with the new ID
                  if (updateContentCallback) {
                    const contentBlocks = [{
                      id: `text_${Date.now()}`,
                      type: 'text',
                      needsApproval: false,
                      data: { text: JSON.stringify(vizMessage) }
                    }];
                    updateContentCallback(vizMessageId, contentBlocks);
                  }

                  // Use the global window functions to open visualizations
                  if ((window as any).openVisualization) {
                    (window as any).openVisualization(visualizations);
                  }
                }
              }
              setExecutionStatus(data.status);
              if (onStatus) {
                onStatus(data.status, data.eventData, data.response_type);  // Pass response_type
              }
            }
          },
          onError: (error) => {
            console.error('Resume streaming error:', error);
            setLoading(false);
            throw error;
          },
          onComplete: () => {
            setLoading(false);
          }
        }
      );

    } catch (error) {
      console.error('Failed to resume streaming:', error);
      setLoading(false);
      throw error;
    }
  };

  const handleSendMessage = async (message: string, _messageHistory: Message[], options?: { usePlanning?: boolean; useExplainer?: boolean; attachedFiles?: File[] }): Promise<HandlerResponse> => {
    // Close any open panels at start
    setExplorerData(null);
    setExplorerOpen(false);
    setVisualizationCharts(null);
    setVisualizationOpen(false);
    setDataFrameOpen(false);
    setDataFrameData(null);
    setLoading(true);
    setExecutionStatus('running');

    // Extract planning and explainer preferences from options (defaults to true)
    const usePlanning = options?.usePlanning ?? true;
    const useExplainer = options?.useExplainer ?? true;

    try {

      let chatThreadId = selectedChatThreadId;
      if (!chatThreadId) {
        chatThreadId = await createNewChatThread(message);
        // Immediately update the ref to avoid race conditions with message persistence
        currentThreadIdRef.current = chatThreadId;
        setSelectedChatThreadId(chatThreadId);
        setCurrentThreadId(chatThreadId);
      } else {
        currentThreadIdRef.current = chatThreadId;
      }

      if (!useStreaming) {
        // Original blocking API call (deprecated - only streaming is supported)
        // @ts-ignore - Non-streaming methods are deprecated
        const response = await GraphService.startGraph({
          human_request: message,
          thread_id: chatThreadId,
          use_planning: usePlanning,
          use_explainer: useExplainer
        });
        // @ts-ignore - Non-streaming response type
        if (response.data?.run_status === 'user_feedback') {
          setExecutionStatus('user_feedback');
          setLoading(false);

          const plan = response.data?.plan || response.data?.assistant_response || 'Plan generated - awaiting approval';
          const assistantResponse = `**Plan for your request:**\n\n${plan}\n\n**This plan requires your approval before execution.**`;

          return {
            message: assistantResponse,
            needsApproval: true,
            backendMessageId: response.data?.assistant_message_id // Pass backend message ID
          };
          // @ts-ignore - Non-streaming response type
        } else if (response.data?.run_status === 'finished') {
          setExecutionStatus('finished');
          setLoading(false);

          const assistantResponse = response.data?.assistant_response || 'Task completed successfully.'
          // Do not auto-open panels; allow clicking message card to open

          return {
            message: assistantResponse,
            needsApproval: false,
            checkpoint_id: response.data?.checkpoint_id, // Add checkpoint ID for both explorer and visualization messages
            ...(response.data?.steps && response.data.steps.length > 0 ? { explorerData: response.data } : {}),
            ...(response.data?.visualizations && response.data.visualizations.length > 0 ? { visualizations: response.data.visualizations } : {})
          };
        } else if (response.data?.run_status === 'error') {
          throw new Error(response.data?.error || 'An error occurred while processing your request.');
        }

        const assistantResponse = response.data?.assistant_response || 'Processing...';
        // Message will be stored automatically by ChatComponent via onMessageCreated
        return {
          message: assistantResponse,
          needsApproval: false
        };
      } else {
        // Streaming API call - return a promise that will be handled by the streaming logic
        const startResponse = await GraphService.startStreamingGraph({
          human_request: message,
          thread_id: chatThreadId,
          use_planning: usePlanning,
          use_explainer: useExplainer
        });
        setCurrentThreadId(startResponse.data?.thread_id || '');

        return {
          message: '', // This will be filled by streaming
          needsApproval: false, // This will be determined by streaming status
          isStreaming: true,
          backendMessageId: startResponse.data?.assistant_message_id as string | undefined,
          streamingHandler: async (
            streamingMessageId: number,
            updateContentCallback: (id: number, contentBlocks: any[]) => void,
            onStatus?: (status: 'user_feedback' | 'finished' | 'running' | 'error' | 'tool_call' | 'tool_result' | 'completed_payload' | 'visualizations_ready' | 'content_block', eventData?: string, responseType?: 'answer' | 'replan' | 'cancel') => void
          ) => {
            await startStreamingForMessage(message, streamingMessageId, chatThreadId, updateContentCallback, onStatus, usePlanning, useExplainer, startResponse);
          }
        };
      }
    } catch (error) {
      console.error('Error in handleSendMessage:', error);
      setLoading(false);
      throw error;
    }
  };

  const handleApprove = async (_content: string, message: Message): Promise<HandlerResponse> => {
    const threadId = currentThreadIdRef.current || currentThreadId || selectedChatThreadId || message.threadId;

    if (!threadId) {
      throw new Error('No active thread to approve');
    }

    try {
      setLoading(true);
      setExecutionStatus('running');

      if (!useStreaming) {
        // Original blocking approach
        const response = await GraphService.approveAndContinue(threadId);

        if (response.data?.run_status === 'finished') {
          const finalResponse = response.data?.assistant_response || 'Task completed successfully.';

          let detailedResponse = finalResponse;
          if (response.data?.steps && response.data.steps.length > 0) {
            detailedResponse += `\n\n**Execution Summary:**\n`;
            detailedResponse += `- Steps executed: ${response.data.steps.length}\n`;
            if (response.data.overall_confidence) {
              detailedResponse += `- Overall confidence: ${(response.data.overall_confidence * 100).toFixed(1)}%\n`;
            }
            if (response.data.total_time) {
              detailedResponse += `- Total time: ${response.data.total_time.toFixed(2)}s\n`;
            }
          }

          // Do not auto-open panels; allow clicking message card to open

          return {
            message: detailedResponse,
            needsApproval: false,
            checkpoint_id: response.data?.checkpoint_id, // Add checkpoint ID for both explorer and visualization messages
            ...(response.data?.steps && response.data.steps.length > 0 ? { explorerData: response.data } : {}),
            ...(response.data?.visualizations && response.data.visualizations.length > 0 ? { visualizations: response.data.visualizations } : {})
          };

        } else if (response.data?.run_status === 'error') {
          throw new Error(response.data?.error || 'An error occurred during execution');
        } else {
          const assistantResponse = response.data?.assistant_response || 'Execution in progress...';
          // Message will be stored automatically by ChatComponent via onMessageCreated
          return {
            message: assistantResponse,
            needsApproval: false
          };
        }
      } else {
        // Streaming approach
        const resumeResponse = await GraphService.resumeStreamingGraph({
          thread_id: threadId,
          review_action: ApprovalStatus.APPROVED,
          human_comment: undefined
        });
        setCurrentThreadId(resumeResponse.data?.thread_id || '');

        return {
          message: '', // This will be filled by streaming
          needsApproval: false, // This will be determined by streaming status
          isStreaming: true,
          backendMessageId: resumeResponse.data?.assistant_message_id as string | undefined,
          streamingHandler: async (
            streamingMessageId: number,
            updateContentCallback: (id: number, contentBlocks: any[]) => void,
            onStatus?: (status: 'user_feedback' | 'finished' | 'running' | 'error' | 'tool_call' | 'tool_result' | 'completed_payload' | 'visualizations_ready' | 'content_block', eventData?: string, responseType?: 'answer' | 'replan' | 'cancel') => void
          ) => {
            await resumeStreamingForMessage(threadId, ApprovalStatus.APPROVED, undefined, streamingMessageId, updateContentCallback, onStatus, resumeResponse);
          }
        };
      }

    } catch (error) {
      console.error('Error approving plan:', error);
      setLoading(false);
      throw error;
    }
  };

  const handleFeedback = async (content: string, _message: Message): Promise<HandlerResponse> => {

    const threadId = currentThreadIdRef.current || currentThreadId || selectedChatThreadId;

    if (!threadId) {
      throw new Error('No active thread to provide feedback for');
    }

    try {

      if (!useStreaming) {
        // Original blocking approach
        const response = await GraphService.provideFeedbackAndContinue(threadId, content);

        if (response.data?.run_status === 'user_feedback') {
          const responseMessage = response.data?.assistant_response || response.data?.plan || 'Response generated';
          const needsApproval = response.data?.response_type === 'replan';


          return {
            message: responseMessage,
            needsApproval: needsApproval,
            response_type: response.data?.response_type,
            backendMessageId: response.data?.assistant_message_id as string | undefined // Include backend message ID for replan
          };

        } else if (response.data?.run_status === 'finished') {
          const finalResponse = response.data?.assistant_response || 'Task completed successfully after feedback.';

          let detailedResponse = finalResponse;
          if (response.data?.steps && response.data.steps.length > 0) {
            detailedResponse += `\n\n**Execution Summary:**\n`;
            detailedResponse += `- Steps executed: ${response.data.steps.length}\n`;
            if (response.data?.overall_confidence) {
              detailedResponse += `- Overall confidence: ${(response.data?.overall_confidence * 100).toFixed(1)}%\n`;
            }
            if (response.data?.total_time) {
              detailedResponse += `- Total time: ${response.data?.total_time.toFixed(2)}s\n`;
            }
          }

          // Do not auto-open panels; allow clicking message card to open

          return {
            message: detailedResponse,
            needsApproval: false,
            checkpoint_id: response.data?.checkpoint_id, // Add checkpoint ID for both explorer and visualization messages
            ...(response.data?.steps && response.data.steps.length > 0 ? { explorerData: response.data } : {}),
            ...(response.data?.visualizations && response.data.visualizations.length > 0 ? { visualizations: response.data.visualizations } : {})
          };

        } else if (response.data?.run_status === 'error') {
          throw new Error(response.data?.error || 'An error occurred during execution');
        } else {
          const assistantResponse = response.data?.assistant_response || 'Processing feedback...';
          return {
            message: assistantResponse,
            needsApproval: false
          };
        }
      } else {

        const resumeResponse = await GraphService.resumeStreamingGraph({
          thread_id: threadId,
          review_action: ApprovalStatus.FEEDBACK,
          human_comment: content
        });
        setCurrentThreadId(resumeResponse.data?.thread_id || '');

        return {
          message: '', // This will be filled by streaming
          needsApproval: false, // This will be determined by streaming status
          isStreaming: true,
          backendMessageId: resumeResponse.data?.assistant_message_id as string | undefined,
          streamingHandler: async (
            streamingMessageId: number,
            updateContentCallback: (id: number, contentBlocks: any[]) => void,
            onStatus?: (status: 'user_feedback' | 'finished' | 'running' | 'error' | 'tool_call' | 'tool_result' | 'completed_payload' | 'visualizations_ready' | 'content_block', eventData?: string, responseType?: 'answer' | 'replan' | 'cancel') => void
          ) => {
            await resumeStreamingForMessage(threadId, ApprovalStatus.FEEDBACK, content, streamingMessageId, updateContentCallback, onStatus, resumeResponse);
          }
        };
      }

    } catch (error) {
      console.error('Error providing feedback:', error);
      throw error;
    }
  };

  const handleCancel = async (_content: string, message: Message): Promise<string> => {

    const threadId = currentThreadIdRef.current || currentThreadId || selectedChatThreadId || message.threadId;

    if (!threadId) {
      throw new Error('No active thread to cancel');
    }

    try {

      await GraphService.cancelExecution(threadId);

      return `**Execution Cancelled**\n\nThe task has been cancelled and will not be executed.`;

    } catch (error) {
      console.error('Error cancelling execution:', error);
      throw error;
    }
  };

  const handleRetry = async (message: Message): Promise<HandlerResponse | void> => {

    const threadId = message.threadId || currentThreadId;

    if (!threadId) {
      throw new Error('No thread ID available for retry');
    }

    try {
      let response;

      if (message.messageStatus === 'pending') {
        response = await GraphService.approveAndContinue(threadId);
      } else if (message.messageStatus === 'rejected') {
        response = await GraphService.provideFeedbackAndContinue(threadId, 'Retrying previous action');
      } else {
        throw new Error('Cannot retry message with status: ' + message.messageStatus);
      }

      if (response.data?.run_status === 'finished') {
        const finalResponse = response.data?.assistant_response || 'Task completed successfully after retry.';

        let detailedResponse = finalResponse;
        if (response.data?.steps && response.data.steps.length > 0) {
          detailedResponse += `\n\n**Execution Summary:**\n`;
          detailedResponse += `- Steps executed: ${response.data.steps.length}\n`;
          if (response.data?.overall_confidence) {
            detailedResponse += `- Overall confidence: ${(response.data?.overall_confidence * 100).toFixed(1)}%\n`;
          }
          if (response.data?.total_time) {
            detailedResponse += `- Total time: ${response.data?.total_time.toFixed(2)}s\n`;
          }
        }


        return { message: detailedResponse, needsApproval: false };

      } else if (response.data?.run_status === 'user_feedback') {
        const newPlan = response.data?.assistant_response || response.data?.plan || 'New plan generated after retry - awaiting approval';
        const planMessage = `**Plan after retry:**\n\n${newPlan}\n\n⚠️ **This plan requires your approval before execution.**`;



        return { message: planMessage || '', needsApproval: true };

      } else if (response.data?.run_status === 'error') {
        throw new Error(response.data?.error || 'An error occurred during retry');
      }

      const fallbackResponse = response.data?.assistant_response || 'Retry completed.';

      return { message: fallbackResponse, needsApproval: false };

    } catch (error) {
      console.error('Error during retry:', error);
      throw error;
    }
  };

  // Handle thread selection
  const handleThreadSelect = async (threadId: string | null) => {
    if (threadId === selectedChatThreadId) return;

    setLoadingThread(true);
    try {
      setSelectedChatThreadId(threadId);
      currentThreadIdRef.current = threadId;
      setShowExecutionHistory(false); // Return to chat component when selecting a thread

      if (threadId) {
        const response = await ConversationService.restoreConversation(threadId);
        const { thread_id, title, messages } = response.data || {};
        const data_context = response.data?.data_context;
        const convertedMessages = convertChatHistoryToMessages(messages || []);
        setRestoredMessages(convertedMessages);

        // Set the thread title
        setCurrentThreadTitle(title || 'Untitled Thread');

        setCurrentThreadId(threadId);
        setExplorerData(null);
        setExplorerOpen(false);
        setVisualizationCharts(null);
        setVisualizationOpen(false);
        setDataFrameOpen(false);
        setDataFrameData(null);

        // Check for data context: try to load preview silently if DataFrame still exists in Redis.
        // If missing, offer to recreate it using the original SQL query and also refresh agent state.
        if (data_context && data_context.df_id) {
          try {
            const previewResponse = await DataService.getDataFramePreview(data_context.df_id);
            setDataFrameData(previewResponse.data || null);
            // Do NOT auto-open the panel; user can open via the button in the input form.
          } catch (err: any) {
            console.error("Failed to load data frame preview:", err);
            const hasSql = !!data_context.sql_query;
            if (hasSql) {
              const shouldReload = window.confirm(
                "Previous data context has expired or is unavailable. Do you want to recreate it using the original SQL query?"
              );
              if (shouldReload) {
                try {
                  const recreatedResponse = await DataService.recreateDataFrame(threadId, data_context.sql_query);
                  setDataFrameData(recreatedResponse.data || null);
                  // Again, do not auto-open; user uses the Data Context button.
                } catch (reloadErr: any) {
                  console.error("Failed to recreate data context:", reloadErr);
                  alert("Failed to recreate data context. Please rerun your original request.");
                }
              }
            }
          }
        }
      } else {
        // Handle null threadId (e.g., when thread is deleted)
        // Clear all chat state similar to handleNewThread
        setRestoredMessages([]);
        setCurrentThreadTitle('');
        setChatKey(prev => prev + 1); // Force remount of ChatComponent to clear internal state
        setCurrentThreadId(null);
        setExplorerData(null);
        setExplorerOpen(false);
        setVisualizationCharts(null);
        setVisualizationOpen(false);
        setDataFrameOpen(false);
        setDataFrameData(null);
      }
    } catch (error) {
      console.error('Error selecting thread:', error);
      alert('Failed to load chat thread');
    } finally {
      setLoadingThread(false);
    }
  };

  const handleExecutionHistoryClick = () => {
    setShowExecutionHistory(true);
  };

  const handleExecutionHistoryBack = () => {
    setShowExecutionHistory(false);
  };

  const handleCheckpointClick = async (checkpointId: string, threadId: string) => {
    try {
      // Fetch explorer data for the selected checkpoint
      const explorerResponse = await ExplorerService.getExplorerData(threadId, checkpointId);
      setExplorerData(explorerResponse?.data);
      setExplorerOpen(true);
      setVisualizationOpen(false); // Ensure visualization panel is closed
      setDataFrameOpen(false);
    } catch (error) {
      console.error('Error fetching explorer data for checkpoint:', checkpointId, error);
      // Still open the panel even if fetch fails
      setExplorerOpen(true);
      setVisualizationOpen(false);
    }
  };

  const handleNewThread = () => {
    setSelectedChatThreadId(null);
    currentThreadIdRef.current = null;
    setRestoredMessages([]);
    setCurrentThreadTitle(''); // Clear thread title for new thread
    setChatKey(prev => prev + 1);
    setCurrentThreadId(null);
    setExplorerData(null);
    setExplorerOpen(false);
    setVisualizationCharts(null);
    setVisualizationOpen(false);
    setDataFrameOpen(false);
    setDataFrameData(null);
    setShowExecutionHistory(false);
  };

  // Handle thread title changes
  const handleTitleChange = async (newTitle: string) => {
    if (!selectedChatThreadId) return;

    try {
      // Update the title via API (you'll need to implement this endpoint)
      // await ChatHistoryService.updateThreadTitle(selectedChatThreadId, newTitle);
      setCurrentThreadTitle(newTitle);
    } catch (error) {
      console.error('Failed to update thread title:', error);
      // You might want to show an error message to the user
    }
  };

  return (
    <div className="h-full w-full overflow-hidden">
      {/* Enhanced Sidebar - always visible, expands/collapses */}
      <Sidebar
        selectedThreadId={selectedChatThreadId || undefined}
        onThreadSelect={handleThreadSelect}
        onNewThread={handleNewThread}
        onExpandedChange={setSidebarExpanded}
        onExecutionHistoryClick={handleExecutionHistoryClick}
      />


      <div className={`h-full min-h-0 flex flex-col transition-[margin-left] duration-300 ease-in-out overflow-hidden ml-0 ${sidebarExpanded ? 'md:ml-82' : 'md:ml-14'}`}>
        <div className="w-full h-full flex flex-col min-h-0">
          <div className="flex items-center justify-between px-4 pt-2 pb-1 text-xs text-muted-foreground">
            <div>
              {currentThreadId || selectedChatThreadId && (
                <span className="mr-4">
                  Graph Thread: {currentThreadId || selectedChatThreadId}
                </span>
              )}
              {loadingThread && (
                <span className="text-primary">
                  Loading thread...
                </span>
              )}
            </div>
          </div>

          {/* Chat Container or Execution History */}
          <div className="flex-1 min-h-0">
            <div className="w-full h-full">
              {showExecutionHistory ? (
                <ExecutionHistory
                  onCheckpointClick={handleCheckpointClick}
                  onBack={handleExecutionHistoryBack}
                />
              ) : (
                <ChatComponent
                  key={`chat-approval-${chatKey}`}
                  onSendMessage={handleSendMessage}
                  onApprove={handleApprove}
                  onFeedback={handleFeedback}
                  onCancel={handleCancel}
                  onRetry={handleRetry}
                  currentThreadId={currentThreadId || selectedChatThreadId}
                  initialMessages={restoredMessages}
                  placeholder="Ask me anything..."
                  className="h-full"
                  onMessageUpdated={handleMessageUpdated}
                  threadTitle={currentThreadTitle}
                  onTitleChange={handleTitleChange}
                  sidebarExpanded={sidebarExpanded}
                  hasDataContext={!!dataFrameData}
                  onOpenDataContext={() => setDataFrameOpen(true)}
                />
              )}
            </div>
          </div>
        </div>

        {/* Slide-out Panels (mutually exclusive) */}
        <ExplorerPanel
          open={explorerOpen && !visualizationOpen && !dataFrameOpen}
          onClose={() => setExplorerOpen(false)}
          data={explorerData}
        />
        <VisualizationPanel
          open={visualizationOpen && !explorerOpen && !dataFrameOpen}
          onClose={() => setVisualizationOpen(false)}
          charts={visualizationCharts || []}
        />
        <DataFramePanel
          open={dataFrameOpen && !explorerOpen && !visualizationOpen}
          onClose={() => setDataFrameOpen(false)}
          data={dataFrameData}
        />
      </div>
    </div>
  );
};

export default ChatWithApproval;
