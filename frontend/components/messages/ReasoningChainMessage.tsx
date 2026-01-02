import React, { useState } from 'react';

interface ReasoningStep {
    step_number: number;
    tool_used: string;
    what_happened: string;
    key_finding?: string | null;
}

interface ReasoningChainMessageProps {
    data: {
        steps: ReasoningStep[];
    };
}

export const ReasoningChainMessage: React.FC<ReasoningChainMessageProps> = ({ data }) => {
    const [isExpanded, setIsExpanded] = useState(true);

    return (
        <div className="reasoning-chain-message bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/10 dark:to-indigo-900/10 border border-blue-200 dark:border-blue-800 rounded-lg p-4 my-3">
            {/* Header */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="flex items-center justify-between w-full text-left"
            >
                <div className="flex items-center gap-2">
                    <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                    <h4 className="font-semibold text-blue-900 dark:text-blue-100 text-sm">
                        How I Solved This ({data.steps.length} steps)
                    </h4>
                </div>
                <svg
                    className={`w-4 h-4 text-blue-600 dark:text-blue-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
            </button>

            {/* Steps */}
            {isExpanded && (
                <div className="mt-4 space-y-3">
                    {data.steps.map((step, index) => (
                        <div key={index} className="relative">
                            <div className="flex gap-3">
                                {/* Step number badge */}
                                <div className="flex-shrink-0">
                                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 dark:from-blue-500 dark:to-indigo-500 text-white text-xs font-bold flex items-center justify-center shadow-sm">
                                        {step.step_number}
                                    </div>
                                </div>

                                {/* Step content */}
                                <div className="flex-1 min-w-0 pb-3">
                                    {/* Tool badge */}
                                    <div className="flex items-center gap-2 mb-1.5">
                                        <span className="text-xs font-mono bg-white dark:bg-gray-800 px-2 py-1 rounded border border-blue-200 dark:border-blue-700 text-blue-700 dark:text-blue-300 font-medium">
                                            {step.tool_used}
                                        </span>
                                    </div>

                                    {/* What happened */}
                                    <p className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed">
                                        {step.what_happened}
                                    </p>

                                    {/* Key finding */}
                                    {step.key_finding && (
                                        <div className="mt-2 flex items-start gap-2 bg-blue-100/50 dark:bg-blue-900/20 rounded-md p-2">
                                            <span className="text-sm flex-shrink-0">💡</span>
                                            <p className="text-xs text-blue-800 dark:text-blue-200 leading-relaxed">
                                                {step.key_finding}
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Connector line (except for last step) */}
                            {index < data.steps.length - 1 && (
                                <div
                                    className="absolute left-[13px] top-7 w-0.5 h-full bg-gradient-to-b from-blue-300 to-indigo-300 dark:from-blue-700 dark:to-indigo-700"
                                />
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};
