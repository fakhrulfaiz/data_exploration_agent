import { GraphResponseWithInterrupt, HumanInterrupt } from '@/types/chat';

/**
 * Detect if response contains a tool-level interrupt
 */
export function hasToolInterrupt(response: any): boolean {
    return !!(
        response?.__interrupt__ &&
        response.__interrupt__.length > 0 &&
        response.__interrupt__[0]?.value?.action_request
    );
}

/**
 * Extract tool interrupt from response
 */
export function extractToolInterrupt(response: GraphResponseWithInterrupt): HumanInterrupt | null {
    if (!hasToolInterrupt(response)) {
        return null;
    }

    return response.__interrupt__![0].value;
}

/**
 * Check if response is a plan approval (node-level interrupt)
 */
export function hasPlanApproval(response: any): boolean {
    return response?.run_status === 'user_feedback' && !!response?.plan;
}

/**
 * Detect interrupt type from response
 */
export function detectInterruptType(response: any): 'tool' | 'plan' | 'none' {
    if (hasToolInterrupt(response)) {
        return 'tool';
    }

    if (hasPlanApproval(response)) {
        return 'plan';
    }

    return 'none';
}
