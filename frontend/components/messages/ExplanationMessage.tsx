import React from 'react';

interface PolicyAudit {
    policy_name: string;
    passed: boolean;
    message: string;
    severity: 'info' | 'warning' | 'error';
}

interface ExplanationData {
    decision: string;
    reasoning?: string;
    tool_justification?: string;
    contrastive_explanation?: string;
    data_evidence?: string;
    policy_audits?: PolicyAudit[];
    counterfactual?: string | null;
}

interface ExplanationMessageProps {
    data: ExplanationData;
}

export const ExplanationMessage: React.FC<ExplanationMessageProps> = ({ data }) => {
    return (
        <div className="explanation-message bg-gray-50 dark:bg-gray-900/20 border border-gray-200 dark:border-gray-700 rounded-lg p-4 my-2">
            <div className="flex items-start gap-2 mb-3">
                <div className="flex-shrink-0 mt-0.5">
                    <svg className="w-5 h-5 text-gray-600 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </div>
                <div className="flex-1 min-w-0">
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100 text-sm mb-2">
                        Step Explanation
                    </h4>

                    {/* Decision */}
                    {data.decision && (
                        <div className="mb-2">
                            <p className="text-sm text-gray-800 dark:text-gray-200">
                                {data.decision}
                            </p>
                        </div>
                    )}

                    {/* Reasoning - moved under decision */}
                    {data.reasoning && (
                        <div className="mb-3 pl-3 border-l-2 border-gray-300 dark:border-gray-600">
                            <p className="text-xs text-gray-600 dark:text-gray-400">
                                {data.reasoning}
                            </p>
                        </div>
                    )}

                    {/* Policy Audits */}
                    {data.policy_audits && data.policy_audits.length > 0 && (
                        <div className="mb-3">
                            <span className="text-xs font-medium text-gray-700 dark:text-gray-300 block mb-1.5">
                                Policy Validation:
                            </span>
                            <div className="flex flex-wrap gap-1.5">
                                {data.policy_audits.map((audit, idx) => {
                                    let bgColor = 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300';
                                    let icon = '•';

                                    if (audit.passed) {
                                        bgColor = 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300';
                                        icon = '✓';
                                    } else if (audit.severity === 'warning') {
                                        bgColor = 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300';
                                        icon = '⚠';
                                    } else if (audit.severity === 'error') {
                                        bgColor = 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300';
                                        icon = '✗';
                                    }

                                    return (
                                        <span
                                            key={idx}
                                            className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${bgColor}`}
                                            title={audit.message}
                                        >
                                            <span>{icon}</span>
                                            <span>{audit.policy_name}</span>
                                        </span>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Counterfactual */}
                    {data.counterfactual && (
                        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                            <div className="flex items-start gap-2">
                                <span className="text-xs font-medium text-gray-700 dark:text-gray-300 flex-shrink-0">
                                    💡 What-if:
                                </span>
                                <p className="text-xs italic text-gray-600 dark:text-gray-400">
                                    {data.counterfactual}
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Additional details (collapsible) */}
                    {(data.tool_justification || data.contrastive_explanation || data.data_evidence) && (
                        <details className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                            <summary className="text-xs font-medium text-gray-700 dark:text-gray-300 cursor-pointer hover:text-gray-800 dark:hover:text-gray-200">
                                View detailed explanation
                            </summary>
                            <div className="mt-2 space-y-2 text-xs text-gray-700 dark:text-gray-300">
                                {data.tool_justification && (
                                    <div>
                                        <span className="font-medium">Tool Choice:</span> {data.tool_justification}
                                    </div>
                                )}
                                {data.contrastive_explanation && (
                                    <div>
                                        <span className="font-medium">Alternative:</span> {data.contrastive_explanation}
                                    </div>
                                )}
                                {data.data_evidence && (
                                    <div>
                                        <span className="font-medium">Evidence:</span> {data.data_evidence}
                                    </div>
                                )}
                            </div>
                        </details>
                    )}
                </div>
            </div>
        </div>
    );
};
