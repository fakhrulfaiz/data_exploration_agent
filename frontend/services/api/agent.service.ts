/**
 * Agent Service
 * Handles agent operations and thread management
 */

import { apiClient } from '../client';
import { API_ENDPOINTS, buildUrl } from '../endpoints';
import type {
    AgentRequest,
    AgentResponse,
    StateResponse,
    StateUpdateRequest,
    BulkDeleteRequest,
    BulkDeleteResponse,
    CleanupResponse,
    SuccessResponse,
} from '@/types';

export class AgentService {
    /**
     * Run the agent with a single user message
     */
    static async runAgent(
        message: string,
        sessionId?: string
    ): Promise<AgentResponse> {
        const request: AgentRequest = {
            message,
            session_id: sessionId,
        };
        return apiClient.post<AgentResponse>(API_ENDPOINTS.AGENT.RUN, request);
    }

    /**
     * Delete all checkpoints for a specific thread
     */
    static async deleteThread(threadId: string): Promise<SuccessResponse> {
        return apiClient.delete<SuccessResponse>(
            API_ENDPOINTS.AGENT.DELETE_THREAD(threadId)
        );
    }

    /**
     * Get the current state for a thread
     */
    static async getThreadState(threadId: string): Promise<StateResponse> {
        return apiClient.get<StateResponse>(
            API_ENDPOINTS.AGENT.GET_STATE(threadId)
        );
    }

    /**
     * Update state for an existing thread
     */
    static async updateThreadState(
        threadId: string,
        stateUpdates: Record<string, any>
    ): Promise<SuccessResponse> {
        const request: StateUpdateRequest = { state_updates: stateUpdates };
        return apiClient.post<SuccessResponse>(
            API_ENDPOINTS.AGENT.UPDATE_STATE(threadId),
            request
        );
    }

    /**
     * Delete multiple threads in bulk
     */
    static async deleteMultipleThreads(
        threadIds: string[]
    ): Promise<BulkDeleteResponse> {
        const request: BulkDeleteRequest = { thread_ids: threadIds };
        return apiClient.delete<BulkDeleteResponse>(
            API_ENDPOINTS.AGENT.BULK_DELETE
        );
    }

    /**
     * Clean up checkpoints older than specified days
     */
    static async cleanupOldCheckpoints(
        olderThanDays: number = 30
    ): Promise<CleanupResponse> {
        const url = buildUrl(API_ENDPOINTS.AGENT.CLEANUP_CHECKPOINTS, {
            older_than_days: olderThanDays,
        });
        return apiClient.delete<CleanupResponse>(url);
    }

    /**
     * Get agent service health status
     */
    static async healthCheck(): Promise<any> {
        return apiClient.get<any>(API_ENDPOINTS.AGENT.HEALTH);
    }
}

export default AgentService;
