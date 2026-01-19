import React from 'react';

interface ExplanationData {
    task_completion_status?: string; 
    execution_summary?: string;
    data_evidence?: string;
    confidence_score?: number;
    confidence_factors?: string[];
}

interface ExplanationMessageProps {
    data: ExplanationData;
    onActionClick?: (action: string) => void;
}

export const ExplanationMessage: React.FC<ExplanationMessageProps> = ({ data, onActionClick }) => {
    const [isExpanded, setIsExpanded] = React.useState(false);

    // Determine status badge color
    const getStatusBadge = (status?: string) => {
        if (!status) return null;
        
        let bgColor = 'bg-muted text-muted-foreground';
        let icon = '•';
        
        if (status.toLowerCase().startsWith('success')) {
            bgColor = 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300';
            icon = '✓';
        } else if (status.toLowerCase().startsWith('partial')) {
            bgColor = 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300';
            icon = '⚠';
        } else if (status.toLowerCase().startsWith('failed')) {
            bgColor = 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300';
            icon = '✗';
        } else if (status.toLowerCase().startsWith('unknown')) {
            bgColor = 'bg-gray-100 dark:bg-gray-900/30 text-gray-800 dark:text-gray-300';
            icon = '?';
        }
        
        return { bgColor, icon, status };
    };
    
    // P1: Confidence badge helper (No percentage, just label)
    const getConfidenceBadge = (score?: number) => {
        if (score === undefined || score === null) return null;
        
        let bgColor = 'bg-gray-100 dark:bg-gray-900/30 text-gray-800 dark:text-gray-300';
        let label = 'Unknown';
        
        if (score >= 0.8) {
            bgColor = 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300';
            label = 'High';
        } else if (score >= 0.5) {
            bgColor = 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300';
            label = 'Medium';
        } else {
            bgColor = 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300';
            label = 'Low';
        }
        
        return { bgColor, label };
    };
    
    const statusBadge = getStatusBadge(data.task_completion_status);
    const confidenceBadge = getConfidenceBadge(data.confidence_score);
    
    return (
        <div className="explanation-message bg-card border border-border rounded-lg p-3 my-2">
            <div className="flex items-start gap-2">
                <div className="flex-shrink-0 mt-0.5">
                    <svg className="w-5 h-5 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </div>
                <div className="flex-1 min-w-0">
                    {/* Header - Clickable to toggle */}
                    <div 
                        className="flex items-center cursor-pointer hover:opacity-80 select-none pb-1"
                        onClick={() => setIsExpanded(!isExpanded)}
                    >
                        <h4 className="font-semibold text-card-foreground text-sm flex-1">
                            Step Explanation
                        </h4>
                        <div className="text-muted-foreground transition-transform duration-200" style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                            </svg>
                        </div>
                    </div>

                    {/* Collapsible Content */}
                    {isExpanded && (
                        <div className="mt-3 pt-3 border-t border-border animate-in fade-in slide-in-from-top-1 duration-200">
                            {/* Task Completion Status */}
                            {statusBadge && (
                                <div className="mb-3">
                                    <span className="text-xs font-medium text-muted-foreground block mb-1.5">
                                        Task Status:
                                    </span>
                                    <span
                                        className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${statusBadge.bgColor}`}
                                    >
                                        <span>{statusBadge.icon}</span>
                                        <span>{statusBadge.status}</span>
                                    </span>
                                </div>
                            )}

                            {/* Execution Summary */}
                            {data.execution_summary && (
                                <div className="mb-3">
                                    <p className="text-sm text-foreground">
                                        {data.execution_summary}
                                    </p>
                                </div>
                            )}

                            {/* Data Evidence (collapsible) */}
                            {data.data_evidence && (
                                <details className="mb-3 pt-2 border-t border-border/50">
                                    <summary className="text-xs font-medium text-foreground cursor-pointer hover:text-primary list-none flex items-center gap-1">
                                        <span className="opacity-70">▸</span> View evidence
                                    </summary>
                                    <div className="mt-2 text-xs text-foreground pl-3 border-l-2 border-border/50">
                                        {data.data_evidence}
                                    </div>
                                </details>
                            )}

                            {/* Confidence Score (Simplified) */}
                            {confidenceBadge && (
                                <div className="mt-2 pt-2 border-t border-border/50">
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className="text-xs font-medium text-muted-foreground">Confidence:</span>
                                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${confidenceBadge.bgColor}`}>
                                            {confidenceBadge.label}
                                        </span>
                                    </div>
                                    {data.confidence_factors && data.confidence_factors.length > 0 && (
                                        <ul className="text-xs text-muted-foreground list-disc list-inside">
                                            {data.confidence_factors.map((factor, idx) => (
                                                <li key={idx}>{factor}</li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
