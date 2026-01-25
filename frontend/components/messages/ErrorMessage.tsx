"use client";

import React from 'react';

interface ErrorExplanation {
    what_happened: string;
    why_it_happened: string;
    clarifying_questions: string[];
    next_step: string;
}

interface ErrorMessageProps {
    errorExplanation: ErrorExplanation;
}

export function ErrorMessage({ errorExplanation }: ErrorMessageProps) {
    const [showDetails, setShowDetails] = React.useState(false);

    return (
        <div className="my-3 border-l-4 border-red-500 bg-red-50/50 dark:bg-red-950/10 p-4 rounded-r-lg">
            {/* What Happened */}
            <div className="mb-3">
                <p className="text-sm text-foreground leading-relaxed">
                    {errorExplanation.what_happened}
                </p>
            </div>

            {/* Why It Happened - Collapsible */}
            <div className="mb-3">
                <button
                    onClick={() => setShowDetails(!showDetails)}
                    className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors focus:outline-none underline decoration-dotted"
                >
                    {showDetails ? 'Hide details' : 'Why this happened'}
                </button>
                {showDetails && (
                    <div className="mt-2 pl-3 border-l-2 border-muted">
                        <p className="text-sm text-muted-foreground leading-relaxed">
                            {errorExplanation.why_it_happened}
                        </p>
                    </div>
                )}
            </div>

            {/* Clarifying Questions */}
            {errorExplanation.clarifying_questions && errorExplanation.clarifying_questions.length > 0 && (
                <div className="mb-3 pl-3 border-l-2 border-blue-400">
                    <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mb-1.5">
                        Let me clarify:
                    </p>
                    <ul className="space-y-1">
                        {errorExplanation.clarifying_questions.map((question, index) => (
                            <li key={index} className="text-sm text-muted-foreground leading-relaxed">
                                • {question}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Next Step */}
            <div className="pt-2 border-t border-border/50">
                <p className="text-sm text-foreground leading-relaxed">
                    <span className="font-medium">Next:</span> {errorExplanation.next_step || "Try a simpler query or ask me to show you what data is available in the database."}
                </p>
            </div>
        </div>
    );
}
