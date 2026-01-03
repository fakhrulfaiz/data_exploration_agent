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
import GraphFlowPanel from '@/components/graph-flow/GraphFlowPanel';
import { GraphStructure } from '@/types/graph';

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
  const [graphPanelOpen, setGraphPanelOpen] = useState(false);
  const [graphStructure, setGraphStructure] = useState<GraphStructure | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const currentThreadIdRef = useRef<string | null>(null);

  // Thread ID reference to handle race conditions
  useEffect(() => {
    // Observe context value updates
  }, [useStreaming]);

  // Preload graph structure on mount
  useEffect(() => {
    const loadGraphStructure = async () => {
      try {
        const response = await fetch('/api/v1/graph/structure');
        if (response.ok) {
          const result = await response.json();
          if (result.success && result.data) {
            setGraphStructure(result.data);
          }
        }
      } catch (error) {
        console.error('Failed to preload graph structure:', error);
      }
    };
    loadGraphStructure();
  }, []);

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

      return {
        message_id: msg.message_id || String(msg.id || Date.now() + index),
        sender: (msg.sender === 'assistant' ? 'assistant' : 'user'),
        content,
        timestamp: new Date(msg.timestamp),
        threadId: msg.thread_id || selectedChatThreadId || undefined,
        checkpointId: msg.checkpoint_id
      } as Message;
    });
  };


  // restoreDataIfNeeded function removed - was not being used anywhere


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

  const handleDataFrameDetected = async (dfId: string) => {
    try {
      console.log('Fetching DataFrame preview for:', dfId);
      const previewResponse = await DataService.getDataFramePreview(dfId);
      setDataFrameData(previewResponse.data || null);
      console.log('DataFrame preview loaded successfully');
    } catch (err: any) {
      console.error('Failed to load DataFrame preview:', err);

    }
  };

  const handleMessageUpdated = async (msg: Message) => {
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
          // Skip explanation blocks - they don't need approval
          if (block.type === 'explanation') {
            continue;
          }

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
                const messageId = msg.message_id || String(msg.message_id); // Fallback to string id if UUID not available
                await ConversationService.updateBlockApproval(threadId, messageId, block.id, blockUpdates);
              } catch (blockError) {
                console.error(`Failed to update block ${block.id} flags:`, blockError);
              }
            }
          }
        }
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
    streamingMessageId: string,
    chatThreadId: string,
    updateContentCallback: (id: string, contentBlocks: any[]) => void,
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
                    updateContentCallback(String(explorerMessageId), contentBlocks);
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
                    updateContentCallback(String(vizMessageId), contentBlocks);
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
    streamingMessageId?: string,
    updateContentCallback?: (id: string, contentBlocks: any[]) => void,
    onStatus?: (status: 'user_feedback' | 'finished' | 'running' | 'error' | 'tool_call' | 'tool_result' | 'completed_payload' | 'visualizations_ready' | 'content_block', eventData?: string, responseType?: 'answer' | 'replan' | 'cancel') => void,
    preResumeResponse?: GraphResponse
  ): Promise<void> => {
    try {
      const resumeResponse = preResumeResponse ?? await GraphService.resumeStreamingGraph({
        thread_id: threadId,
        review_action: reviewAction,
        human_comment: humanComment,
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
                const graphData = data.data;
                if (graphData && graphData.steps && graphData.steps.length > 0) {
                  // Create a new message with its own ID for explorer data
                  const explorerMessageId = String(Date.now() + Math.floor(Math.random() * 1000));
                  const explorerMessage = {
                    message_id: explorerMessageId,
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
                }
              } else if (data.status === 'visualizations_ready') {
                // Handle visualization data
                const visualizations = data.visualizations || [];
                if (visualizations.length > 0) {
                  // Create a new message with its own ID for visualization data
                  const vizMessageId = String(Date.now() + Math.floor(Math.random() * 1000) + 10000);
                  const vizMessage = {
                    message_id: vizMessageId,
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

                  // Auto-open visualization panel disabled - user can manually click to open
                  // if ((window as any).openVisualization) {
                  //   (window as any).openVisualization(visualizations);
                  // }
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
            backendMessageId: response.data?.assistant_message_id,
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
          needsApproval: false,
          backendMessageId: response.data?.assistant_message_id // Pass backend message ID
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
          backendMessageId: startResponse.data?.assistant_message_id as string,
          streamingHandler: async (
            streamingMessageId: string,
            updateContentCallback: (id: string, contentBlocks: any[]) => void,
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

  const handleApprove = async (messageId: string | undefined, _content: string, message: Message): Promise<HandlerResponse> => {
    const threadId = currentThreadIdRef.current || currentThreadId || selectedChatThreadId || message.threadId;

    if (!threadId) {
      throw new Error('No active thread to approve');
    }

    // Check if this is a tool approval by looking at message content
    const isToolApproval = Array.isArray(message.content) &&
      message.content.some(block => block.type === 'tool_calls');

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
            backendMessageId: response.data?.assistant_message_id,
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
        // Streaming approach - differentiate between tool and plan approvals
        const resumeRequest = isToolApproval
          ? {
            thread_id: threadId,
            message_id: messageId,
            tool_response: { type: 'accept' as const }  // Tool approval
          }
          : {
            thread_id: threadId,
            message_id: messageId,
            review_action: ApprovalStatus.APPROVED,  // Plan approval
            human_comment: undefined
          };

        const resumeResponse = await GraphService.resumeStreamingGraph(resumeRequest);
        setCurrentThreadId(resumeResponse.data?.thread_id || '');

        return {
          message: '', // This will be filled by streaming
          needsApproval: false, // This will be determined by streaming status
          isStreaming: true,
          backendMessageId: resumeResponse.data?.assistant_message_id as string | undefined,
          streamingHandler: async (
            streamingMessageId: string,
            updateContentCallback: (id: string, contentBlocks: any[]) => void,
            onStatus?: (status: 'user_feedback' | 'finished' | 'running' | 'error' | 'tool_call' | 'tool_result' | 'completed_payload' | 'visualizations_ready' | 'content_block', eventData?: string, responseType?: 'answer' | 'replan' | 'cancel') => void
          ) => {
            await resumeStreamingForMessage(threadId, ApprovalStatus.APPROVED, undefined, streamingMessageId, updateContentCallback, onStatus, resumeResponse);
          }
        };
      }

    } catch (error) {
      console.error('Error approving:', error);
      setLoading(false);
      throw error;
    }
  };

  const handleFeedback = async (messageId: string | undefined, content: string, _message: Message): Promise<HandlerResponse> => {

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
            streamingMessageId: string,
            updateContentCallback: (id: string, contentBlocks: any[]) => void,
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

  const handleCancelStream = async (): Promise<void> => {
    try {
      // Close the EventSource connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
        console.log('EventSource connection closed');
      }

      // Call backend cancel endpoint if we have a thread ID
      const threadId = currentThreadIdRef.current || currentThreadId || selectedChatThreadId;
      if (threadId) {
        try {
          await GraphService.cancelStream(threadId);
          console.log('Stream cancelled on backend for thread:', threadId);
        } catch (error) {
          console.error('Failed to cancel stream on backend:', error);
          // Don't throw - EventSource is already closed, which is the important part
        }
      }

      // Reset states
      setLoading(false);
      setExecutionStatus('finished');
    } catch (error) {
      console.error('Error cancelling stream:', error);
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
                  onDataFrameDetected={handleDataFrameDetected}
                  onCancelStream={handleCancelStream}
                  onToggleGraphPanel={() => setGraphPanelOpen(!graphPanelOpen)}
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
        <GraphFlowPanel
          open={graphPanelOpen}
          onClose={() => setGraphPanelOpen(false)}
          threadId={currentThreadId || selectedChatThreadId || undefined}
          graphStructure={graphStructure}
        />
      </div>
    </div>
  );
};

export default ChatWithApproval;
