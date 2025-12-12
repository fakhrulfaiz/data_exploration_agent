/**
 * Helper utilities for working with status values across the frontend
 */

// Status display helpers
export function getStatusColor(status: string): string {
  switch (status) {
    case 'user_feedback':
      return 'text-yellow-600 bg-yellow-50';
    case 'running':
      return 'text-blue-600 bg-blue-50';
    case 'finished':
    case 'completed':
      return 'text-green-600 bg-green-50';
    case 'error':
      return 'text-red-600 bg-red-50';
    case 'cancelled':
      return 'text-gray-600 bg-gray-50';
    default:
      return 'text-gray-600 bg-gray-50';
  }
}

export function getStatusDisplayName(status: string): string {
  switch (status) {
    case 'user_feedback':
      return 'Awaiting Approval';
    case 'running':
      return 'Running';
    case 'finished':
      return 'Completed';
    case 'error':
      return 'Error';
    case 'cancelled':
      return 'Cancelled';
    case 'approved':
      return 'Approved';
    case 'feedback':
      return 'Needs Revision';
    case 'unknown':
      return 'Unknown';
    default:
      return status.charAt(0).toUpperCase() + status.slice(1);
  }
}

export function getStatusDescription(status: string): string {
  switch (status) {
    case 'user_feedback':
      return 'Waiting for human approval or feedback';
    case 'running':
      return 'Graph is actively executing';
    case 'finished':
      return 'Graph execution completed successfully';
    case 'error':
      return 'Graph execution failed with an error';
    case 'approved':
      return 'Human approved the plan';
    case 'feedback':
      return 'Human provided feedback for revision';
    case 'cancelled':
      return 'Human cancelled the operation';
    case 'unknown':
      return 'Status not yet determined';
    default:
      return 'Unknown status';
  }
}

export function isActiveStatus(status: string): boolean {
  return status === 'running' || status === 'user_feedback';
}

export function isCompletedStatus(status: string): boolean {
  return status === 'finished' || status === 'completed';
}

export function isErrorStatus(status: string): boolean {
  return status === 'error';
}
