/**
 * API Client - Modern fetch-based HTTP client with error handling
 */

import { createClient } from '@/utils/supabase/client';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

export interface ApiError {
    status: string;
    message: string;
    errors?: Array<{
        code: string;
        message: string;
    }>;
}

export class ApiClient {
    private baseUrl: string;
    private supabase = createClient();

    constructor(baseUrl: string = BASE_URL) {
        this.baseUrl = baseUrl;
    }

    /**
     * Get authorization header with Supabase JWT token
     */
    private async getAuthHeaders(): Promise<Record<string, string>> {
        try {
            const { data: { session } } = await this.supabase.auth.getSession();

            if (session?.access_token) {
                return {
                    'Authorization': `Bearer ${session.access_token}`
                };
            }
        } catch (error) {
            console.warn('Failed to get auth token:', error);
        }
        return {};
    }

    /**
     * Generic request method
     */
    private async request<T>(
        endpoint: string,
        options: RequestInit = {}
    ): Promise<T> {
        const url = `${this.baseUrl}${endpoint}`;

        // Get auth headers (like an interceptor)
        const authHeaders = await this.getAuthHeaders();

        const config: RequestInit = {
            ...options,
            credentials: 'include', // Include cookies for auth
            headers: {
                'Content-Type': 'application/json',
                ...authHeaders,
                ...options.headers,
            },
        };

        try {
            const response = await fetch(url, config);

            // Handle non-JSON responses
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return {} as T;
            }

            const data = await response.json();

            // Check if response indicates an error
            if (!response.ok || data.status === 'error') {
                const error: ApiError = {
                    status: data.status || 'error',
                    message: data.message || `HTTP ${response.status}: ${response.statusText}`,
                    errors: data.errors,
                };
                throw error;
            }

            return data as T;
        } catch (error) {
            // Re-throw ApiError as-is
            if ((error as ApiError).status) {
                throw error;
            }

            // Wrap other errors
            throw {
                status: 'error',
                message: error instanceof Error ? error.message : 'Unknown error occurred',
            } as ApiError;
        }
    }

    /**
     * GET request
     */
    async get<T>(endpoint: string): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'GET',
        });
    }

    /**
     * POST request
     */
    async post<T>(endpoint: string, data?: unknown): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'POST',
            body: data ? JSON.stringify(data) : undefined,
        });
    }

    /**
     * PUT request
     */
    async put<T>(endpoint: string, data?: unknown): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'PUT',
            body: data ? JSON.stringify(data) : undefined,
        });
    }

    /**
     * PATCH request
     */
    async patch<T>(endpoint: string, data?: unknown): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'PATCH',
            body: data ? JSON.stringify(data) : undefined,
        });
    }

    /**
     * DELETE request
     */
    async delete<T>(endpoint: string): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'DELETE',
        });
    }
}

// Export singleton instance
export const apiClient = new ApiClient();
