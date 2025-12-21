/**
 * Graph Service
 * Handles graph execution with SSE streaming support
 */

import { apiClient } from '../client';
import { API_ENDPOINTS } from '../endpoints';
import {
    StartGraphRequest,
    ResumeGraphRequest,
    GraphResponse,
    ApprovalStatus,
    StreamCallbacks,
} from '@/types';

// Get the base URL from the environment
const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

// Extend the Window interface to include our custom property
declare global {
    interface Window {
        _hasReceivedStatusEvent?: { [url: string]: boolean };
    }
}

export class GraphService {
    /**
     * Start streaming graph execution
     */
    static async startStreamingGraph(
        request: StartGraphRequest
    ): Promise<GraphResponse> {
        return apiClient.post<GraphResponse>(
            API_ENDPOINTS.GRAPH.STREAM.START,
            request
        );
    }

    /**
     * Resume streaming graph execution
     */
    static async resumeStreamingGraph(
        request: ResumeGraphRequest
    ): Promise<GraphResponse> {
        return apiClient.post<GraphResponse>(
            API_ENDPOINTS.GRAPH.STREAM.RESUME,
            request
        );
    }

    /**
     * Approve and continue execution
     */
    static async approveAndContinue(threadId: string, messageId?: string): Promise<GraphResponse> {
        return this.resumeStreamingGraph({
            thread_id: threadId,
            review_action: 'approved' as ApprovalStatus,
            message_id: messageId,
        });
    }

    /**
     * Provide feedback and continue execution
     */
    static async provideFeedbackAndContinue(
        threadId: string,
        feedback: string
    ): Promise<GraphResponse> {
        return this.resumeStreamingGraph({
            thread_id: threadId,
            review_action: 'feedback' as ApprovalStatus,
            human_comment: feedback,
        });
    }

    /**
     * Cancel execution
     */
    static async cancelExecution(threadId: string): Promise<GraphResponse> {
        return this.resumeStreamingGraph({
            thread_id: threadId,
            review_action: ApprovalStatus.REJECTED,
        });
    }

    /**
     * Stream SSE events from the graph execution
     * Returns EventSource for connection management
     */
    static streamResponse(
        threadId: string,
        callbacks: StreamCallbacks
    ): EventSource {
        const { onMessage, onError, onComplete } = callbacks;

        // Create EventSource connection to the streaming endpoint
        const eventSource = new EventSource(
            `${BASE_URL}${API_ENDPOINTS.GRAPH.STREAM.STREAM(threadId)}`
        );

        // Enhanced error handling and recovery
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 3;
        let lastHeartbeat = Date.now();
        const heartbeatTimeout = 30000; // 30 seconds

        // Heartbeat monitoring
        const heartbeatInterval = setInterval(() => {
            if (Date.now() - lastHeartbeat > heartbeatTimeout) {
                console.warn('⚠️ Stream heartbeat timeout, connection may be stale');
                clearInterval(heartbeatInterval);
                eventSource.close();
                onError(new Error('Stream connection timeout'));
            }
        }, 5000);

        // Handle content_block events (new structured content)
        eventSource.addEventListener('content_block', (event) => {
            try {
                lastHeartbeat = Date.now(); // Update heartbeat
                const blockData = JSON.parse(event.data);
                // Pass the content_block event to the callback with a special status
                onMessage({
                    status: 'content_block',
                    eventData: event.data,
                    blockData: blockData,
                });
            } catch (error) {
                console.error(
                    'Error parsing content_block event:',
                    error,
                    'Raw data:',
                    event.data
                );
                onError(error as Error);
            }
        });

        // Handle status events (user_feedback, finished)
        eventSource.addEventListener('status', (event) => {
            try {
                lastHeartbeat = Date.now(); // Update heartbeat
                const data = JSON.parse(event.data);
                onMessage({
                    status: data.status,
                    response_type: data.response_type,
                });

                if (!window._hasReceivedStatusEvent) {
                    window._hasReceivedStatusEvent = {};
                }
                window._hasReceivedStatusEvent[eventSource.url] = true;
                console.log(
                    '✅ Received status event, marking connection for normal closure'
                );
            } catch (error) {
                console.error(
                    '❌ Error parsing status event:',
                    error,
                    'Raw data:',
                    event.data
                );
                onError(error as Error);
            }
        });

        // Handle completed events with final payload wrapper
        eventSource.addEventListener('completed', (event) => {
            try {
                const payload = JSON.parse((event as MessageEvent).data);
                const inner = payload && payload.data ? payload.data : payload;

                onMessage({ status: 'completed_payload', graph: inner });
                // Mark normal closure
                if (!window._hasReceivedStatusEvent) {
                    window._hasReceivedStatusEvent = {};
                }
                window._hasReceivedStatusEvent[eventSource.url] = true;
            } catch (error) {
                console.error(
                    'Error parsing completed event:',
                    error,
                    'Raw data:',
                    (event as MessageEvent).data
                );
                onError(error as Error);
            }
        });

        // Handle visualizations_ready events
        eventSource.addEventListener('visualizations_ready', (event) => {
            try {
                const payload = JSON.parse((event as MessageEvent).data);
                const inner = payload && payload.data ? payload.data : payload;
                onMessage({
                    status: 'visualizations_ready',
                    visualizations: inner?.visualizations || [],
                    thread_id: inner?.thread_id,
                    checkpoint_id: inner?.checkpoint_id,
                    types: inner?.types,
                });
            } catch (error) {
                console.error(
                    'Error parsing visualizations_ready event:',
                    error,
                    'Raw data:',
                    (event as MessageEvent).data
                );
                onError(error as Error);
            }
        });

        // Handle start/resume events
        eventSource.addEventListener('start', (event) => {
            console.log('Stream started:', event.data);
        });

        eventSource.addEventListener('resume', (event) => {
            console.log('Stream resumed:', event.data);
        });

        // Handle message events (complete messages)
        eventSource.addEventListener('message', (event) => {
            try {
                const data = JSON.parse(event.data);
                onMessage({
                    content: data.content,
                    node: data.node,
                    type: data.type || 'message',
                });
            } catch (error) {
                console.error(
                    'Error parsing message event:',
                    error,
                    'Raw data:',
                    event.data
                );
                onError(error as Error);
            }
        });

        // Handle tool call events
        eventSource.addEventListener('tool_call', (event) => {
            try {
                lastHeartbeat = Date.now();
                onMessage({
                    status: 'tool_call',
                    eventData: event.data,
                });
            } catch (error) {
                console.error(
                    'Error parsing tool_call event:',
                    error,
                    'Raw data:',
                    event.data
                );
                onError(error as Error);
            }
        });

        // Handle tool result events
        eventSource.addEventListener('tool_result', (event) => {
            try {
                lastHeartbeat = Date.now();
                console.log('✅ FRONTEND: Received tool_result event:', event.data);
                const data = JSON.parse(event.data);
                console.log('✅ FRONTEND: Parsed tool_result data:', data);
                // Pass through as status event so it reaches onStatus callback
                onMessage({
                    status: 'tool_result',
                    eventData: event.data, // Pass the raw JSON string so ChatComponent can parse it
                });
            } catch (error) {
                console.error(
                    'Error parsing tool_result event:',
                    error,
                    'Raw data:',
                    event.data
                );
                onError(error as Error);
            }
        });

        // Handle errors with enhanced recovery
        eventSource.onerror = (error) => {
            console.log(
                '🔄 SSE connection state change - readyState:',
                eventSource.readyState
            );
            clearInterval(heartbeatInterval); // Clear heartbeat monitoring

            // Check if we've received a status event indicating completion
            const hasReceivedStatusEvent =
                window._hasReceivedStatusEvent &&
                window._hasReceivedStatusEvent[eventSource.url];

            if (hasReceivedStatusEvent) {
                console.log(
                    '✅ Stream completed normally after receiving status event'
                );
                eventSource.close();
                onComplete();
                return;
            }

            // Handle reconnection attempts for transient errors
            if (
                eventSource.readyState === EventSource.CONNECTING &&
                reconnectAttempts < maxReconnectAttempts
            ) {
                reconnectAttempts++;
                console.log(
                    `🔄 Reconnection attempt ${reconnectAttempts}/${maxReconnectAttempts}`
                );

                // Wait before next attempt with exponential backoff
                setTimeout(() => {
                    if (eventSource.readyState === EventSource.CLOSED) {
                        console.log('🔄 Attempting to recover stream connection...');
                        // Note: EventSource handles reconnection automatically,
                        // but we can implement custom recovery logic here if needed
                    }
                }, Math.pow(2, reconnectAttempts) * 1000);
                return;
            }

            // Only call the error callback if it's a real error, not a normal close
            if (
                eventSource.readyState !== EventSource.CLOSED &&
                eventSource.readyState !== EventSource.CONNECTING
            ) {
                console.error('❌ SSE connection error:', error);
                eventSource.close();

                // Enhanced error messaging
                const errorMessage =
                    reconnectAttempts >= maxReconnectAttempts
                        ? `Connection failed after ${maxReconnectAttempts} retry attempts`
                        : 'Connection error or server disconnected';

                onError(new Error(errorMessage));
            } else {
                // If it's a normal close or reconnecting, call the complete callback
                console.log('✅ Stream completed normally');
                onComplete();
            }
        };

        // Return EventSource for connection management
        return eventSource;
    }
}

export default GraphService;
