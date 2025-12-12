/**
 * Explorer Service
 * Handles explorer data operations
 */

import { apiClient } from '../client';
import { API_ENDPOINTS, buildUrl } from '../endpoints';

export interface ExplorerData {
    thread_id: string;
    checkpoint_id: string;
    data?: any;
}

export interface ExplorerResponse {
    status?: string;
    message?: string;
    data?: ExplorerData;
    errors?: Array<{ code: string; message: string }>;
}

export class ExplorerService {
    /**
     * Fetch explorer data from a specific checkpoint
     */
    static async getExplorerData(
        threadId: string,
        checkpointId: string
    ): Promise<ExplorerResponse> {
        const url = buildUrl(API_ENDPOINTS.GRAPH.EXPLORER, {
            thread_id: threadId,
            checkpoint_id: checkpointId,
        });
        return apiClient.get<ExplorerResponse>(url);
    }
}

export default ExplorerService;
