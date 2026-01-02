import { apiClient } from '../client';
import { API_ENDPOINTS } from '../endpoints';

export interface ProfileResponse {
    id: string;
    name?: string;
    email?: string;
    nickname?: string;
    role?: string;
    about_user?: string;
    custom_instructions?: string;
    communication_style: string;
}

export interface ProfileUpdateRequest {
    nickname?: string;
    role?: string;
    about_user?: string;
    custom_instructions?: string;
    communication_style?: string;
}

export class ProfileService {
    /**
     * Get user profile
     */
    async getProfile(): Promise<ProfileResponse> {
        return apiClient.get<ProfileResponse>(API_ENDPOINTS.PROFILE.GET);
    }

    /**
     * Update user profile
     */
    async updateProfile(updates: ProfileUpdateRequest): Promise<{ success: boolean; message: string }> {
        return apiClient.put<{ success: boolean; message: string }>(
            API_ENDPOINTS.PROFILE.UPDATE,
            updates
        );
    }
}

export const profileService = new ProfileService();
