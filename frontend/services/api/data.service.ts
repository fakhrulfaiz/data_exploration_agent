/**
 * Data Service
 * Handles DataFrame operations
 */

import { apiClient } from '../client';
import { API_ENDPOINTS } from '../endpoints';
import type {
    DataFramePreviewResponse,
    RecreateDataFrameRequest,
    RecreateDataFrameResponse,
} from '@/types';

export class DataService {
    /**
     * Get a preview (first 100 rows) of the DataFrame from Redis
     */
    static async getDataFramePreview(
        dfId: string
    ): Promise<DataFramePreviewResponse> {
        return apiClient.get<DataFramePreviewResponse>(
            API_ENDPOINTS.DATA.PREVIEW(dfId)
        );
    }

    /**
     * Recreate a DataFrame in Redis using the original SQL query
     * and update the agent's data_context state for the given thread.
     * Returns a preview payload identical to getDataFramePreview.
     */
    static async recreateDataFrame(
        threadId: string,
        sqlQuery: string,
        dfId?: string
    ): Promise<RecreateDataFrameResponse> {
        const request: RecreateDataFrameRequest = {
            thread_id: threadId,
            sql_query: sqlQuery,
            df_id: dfId,
        };
        return apiClient.post<RecreateDataFrameResponse>(
            API_ENDPOINTS.DATA.RECREATE,
            request
        );
    }

    /**
     * Export DataFrame to Excel
     */
    static async exportDataFrame(dfId: string): Promise<Blob> {
        return apiClient.download(
            API_ENDPOINTS.DATA.EXPORT,
            { df_id: dfId }
        );
    }

    /**
     * Download generated plots
     */
    static async downloadPlots(plotUrls: string[]): Promise<Blob> {
        return apiClient.download(
            API_ENDPOINTS.DATA.DOWNLOAD_PLOTS,
            { plot_urls: plotUrls }
        );
    }
}

export default DataService;
