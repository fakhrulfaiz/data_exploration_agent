import { GraphResponseWithInterrupt, HumanInterrupt } from '@/types/chat';

/**
 * Detect if response contains a tool-level interrupt (legacy)
 */
export function hasToolInterrupt(response: any): boolean {
    return !!(
        response?.__interrupt__ &&
        response.__interrupt__.length > 0 &&
        response.__interrupt__[0]?.value?.action_request
    );
}

/**
 * Detect if response contains a tool error interrupt
 */
export function hasToolError(response: any): boolean {
    return !!(
        response?.__interrupt__ &&
        response.__interrupt__.length > 0 &&
        response.__interrupt__[0]?.value?.type === 'tool_error'
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
 * Extract tool error interrupt from response
 */
export function extractToolError(response: any): any | null {
    if (!hasToolError(response)) {
        return null;
    }

    return response.__interrupt__![0].value;
}

/**
 * Check if response is a plan approval (node-level interrupt)
 */
export function hasPlanApproval(response: any): boolean {
    return !!(
        response?.__interrupt__ &&
        response.__interrupt__.length > 0 &&
        response.__interrupt__[0]?.value?.type === 'plan_approval'
    );
}

/**
 * Detect interrupt type from response
 */
export function detectInterruptType(response: any): 'tool' | 'plan' | 'tool_error' | 'none' {
    if (hasToolError(response)) {
        return 'tool_error';
    }

    if (hasToolInterrupt(response)) {
        return 'tool';
    }

    if (hasPlanApproval(response)) {
        return 'plan';
    }

    return 'none';
}
