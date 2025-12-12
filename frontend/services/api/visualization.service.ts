/**
 * Visualization Service
 * Handles visualization data operations
 */

import { apiClient } from '../client';
import { API_ENDPOINTS, buildUrl } from '../endpoints';

export interface VisualizationData {
    thread_id: string;
    checkpoint_id: string;
    visualizations?: any[];
    count?: number;
    types?: string[];
    data?: any; // Keep for backward compatibility
}

export interface VisualizationResponse {
    status?: string;
    message?: string;
    data?: VisualizationData;
    errors?: Array<{ code: string; message: string }>;
}

export class VisualizationService {
    /**
     * Fetch visualization data from a specific checkpoint
     */
    static async getVisualizationData(
        threadId: string,
        checkpointId: string
    ): Promise<VisualizationResponse> {
        const url = buildUrl(API_ENDPOINTS.GRAPH.VISUALIZATION, {
            thread_id: threadId,
            checkpoint_id: checkpointId,
        });
        return apiClient.get<VisualizationResponse>(url);
    }
}

export default VisualizationService;
