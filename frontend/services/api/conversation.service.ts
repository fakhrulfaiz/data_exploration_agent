/**
 * Conversation Service
 * Handles conversation/thread management operations
 */

import { apiClient } from '../client';
import { API_ENDPOINTS, buildUrl } from '../endpoints';
import type {
    CreateConversationRequest,
    UpdateTitleRequest,
    ConversationResponse,
    ConversationListResponse,
    RestoreConversationResponse,
    MessageStatusListResponse,
    MessageStatusUpdateRequest,
    BlockStatusUpdateRequest,
    CheckpointListResponse,
    SuccessResponse,
} from '@/types';

export class ConversationService {
    /**
     * Create a new conversation thread
     */
    static async createConversation(
        request: CreateConversationRequest
    ): Promise<ConversationResponse> {
        return apiClient.post<ConversationResponse>(
            API_ENDPOINTS.CONVERSATION.CREATE,
            request
        );
    }

    /**
     * List all conversation threads
     */
    static async listConversations(
        limit: number = 50,
        skip: number = 0
    ): Promise<ConversationListResponse> {
        const url = buildUrl(API_ENDPOINTS.CONVERSATION.LIST, { limit, skip });
        return apiClient.get<ConversationListResponse>(url);
    }

    /**
     * Get a specific conversation thread
     */
    static async getConversation(threadId: string): Promise<ConversationResponse> {
        return apiClient.get<ConversationResponse>(
            API_ENDPOINTS.CONVERSATION.GET(threadId)
        );
    }

    /**
     * Update conversation title
     */
    static async updateTitle(
        threadId: string,
        title: string
    ): Promise<SuccessResponse> {
        const request: UpdateTitleRequest = { title };
        return apiClient.put<SuccessResponse>(
            API_ENDPOINTS.CONVERSATION.UPDATE_TITLE(threadId),
            request
        );
    }

    /**
     * Delete a conversation thread
     */
    static async deleteConversation(threadId: string): Promise<SuccessResponse> {
        return apiClient.delete<SuccessResponse>(
            API_ENDPOINTS.CONVERSATION.DELETE(threadId)
        );
    }

    /**
     * Restore a conversation thread for continuing conversation
     * Returns the full conversation history with data context if available
     */
    static async restoreConversation(
        threadId: string
    ): Promise<RestoreConversationResponse> {
        return apiClient.get<RestoreConversationResponse>(
            API_ENDPOINTS.CONVERSATION.RESTORE(threadId)
        );
    }

    /**
     * Get status information for all messages in a conversation
     * Helps the frontend sync its local state with the backend
     */
    static async getMessagesStatus(
        threadId: string
    ): Promise<MessageStatusListResponse> {
        return apiClient.get<MessageStatusListResponse>(
            API_ENDPOINTS.CONVERSATION.MESSAGES_STATUS(threadId)
        );
    }

    /**
     * Update message-level status
     * @deprecated Use updateBlockApproval for block-level updates instead
     */
    static async updateMessageStatus(
        threadId: string,
        messageId: string, // Changed to string to accept UUID
        request: MessageStatusUpdateRequest
    ): Promise<SuccessResponse> {
        return apiClient.put<SuccessResponse>(
            API_ENDPOINTS.CONVERSATION.UPDATE_MESSAGE_STATUS(threadId, messageId),
            request
        );
    }

    /**
     * Update block-level approval status
     * Allows updating individual block approval status within a message's content_blocks
     */
    static async updateBlockApproval(
        threadId: string,
        messageId: string, // Changed to string to accept UUID
        blockId: string,
        request: BlockStatusUpdateRequest
    ): Promise<SuccessResponse> {
        return apiClient.patch<SuccessResponse>(
            API_ENDPOINTS.CONVERSATION.UPDATE_BLOCK_APPROVAL(threadId, messageId, blockId),
            request
        );
    }

    /**
     * Mark a message as having an error
     * Useful for handling failed operations or timeout scenarios
     */
    static async markMessageError(
        threadId: string,
        messageId: string, // Changed to string to accept UUID
        errorMessage?: string
    ): Promise<SuccessResponse> {
        const url = buildUrl(
            API_ENDPOINTS.CONVERSATION.MARK_MESSAGE_ERROR(threadId, messageId),
            errorMessage ? { error_message: errorMessage } : {}
        );
        return apiClient.post<SuccessResponse>(url, {});
    }

    /**
     * Get all checkpoints across all threads
     */
    static async listCheckpoints(
        limit: number = 50,
        skip: number = 0
    ): Promise<CheckpointListResponse> {
        const url = buildUrl(API_ENDPOINTS.CONVERSATION.CHECKPOINTS, { limit, skip });
        return apiClient.get<CheckpointListResponse>(url);
    }
}

export default ConversationService;
