/**
 * API Endpoint Constants
 * Matches backend FastAPI routes
 */

export const API_ENDPOINTS = {
    // ==================== Conversation Endpoints ====================
    CONVERSATION: {
        CREATE: '/v1/conversation',
        LIST: '/v1/conversation',
        GET: (threadId: string) => `/v1/conversation/${threadId}`,
        UPDATE_TITLE: (threadId: string) => `/v1/conversation/${threadId}/title`,
        DELETE: (threadId: string) => `/v1/conversation/${threadId}`,
        RESTORE: (threadId: string) => `/v1/conversation/${threadId}/restore`,

        // Message Management
        MESSAGES_STATUS: (threadId: string) => `/v1/conversation/${threadId}/messages/status`,
        UPDATE_MESSAGE_STATUS: (threadId: string, messageId: string) =>
            `/v1/conversation/${threadId}/messages/${messageId}/status`,
        UPDATE_BLOCK_APPROVAL: (threadId: string, messageId: string, blockId: string) =>
            `/v1/conversation/${threadId}/messages/${messageId}/blocks/${blockId}/approval`,
        MARK_MESSAGE_ERROR: (threadId: string, messageId: string) =>
            `/v1/conversation/${threadId}/messages/${messageId}/error`,

        // Checkpoints
        CHECKPOINTS: '/v1/conversation/checkpoints',
    },

    // ==================== Agent Endpoints ====================
    AGENT: {
        RUN: '/v1/agent/run',
        DELETE_THREAD: (threadId: string) => `/v1/agent/threads/${threadId}`,
        GET_STATE: (threadId: string) => `/v1/agent/threads/${threadId}/state`,
        UPDATE_STATE: (threadId: string) => `/v1/agent/threads/${threadId}/state`,
        BULK_DELETE: '/v1/agent/threads/bulk',
        CLEANUP_CHECKPOINTS: '/v1/agent/checkpoints/cleanup',
        HEALTH: '/v1/agent/health',
    },

    // ==================== Data Endpoints ====================
    DATA: {
        PREVIEW: (dfId: string) => `/v1/data/${dfId}/preview`,
        RECREATE: '/v1/data/recreate',
    },

    // ==================== Graph Endpoints ====================
    GRAPH: {
        STREAM: {
            START: '/v1/graph/stream/start',
            RESUME: '/v1/graph/stream/resume',
            STREAM: (threadId: string) => `/v1/graph/stream/${threadId}`,
            RESULT: (threadId: string) => `/v1/graph/stream/result/${threadId}`,
            CANCEL: (threadId: string) => `/v1/graph/stream/cancel/${threadId}`,
        },
        EXPLORER: '/v1/graph/explorer',
        VISUALIZATION: '/v1/graph/visualization',
    },
} as const;

/**
 * Helper function to build URLs with query parameters
 */
export const buildUrl = (
    endpoint: string,
    params?: Record<string, string | number | boolean>
): string => {
    if (!params) return endpoint;

    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        searchParams.append(key, value.toString());
    });

    return `${endpoint}?${searchParams.toString()}`;
};

export default API_ENDPOINTS;
