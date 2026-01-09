"use client";

import React from 'react';
import { AlertCircle, AlertTriangle, Lightbulb, ArrowRight, ChevronDown, ChevronRight } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

interface ErrorExplanation {
    what_happened: string;
    why_it_happened: string;
    what_was_attempted: string;
    alternative_suggestions: string[];
    user_action_needed: string;
    technical_details?: string;
}

interface ErrorMessageProps {
    errorExplanation: ErrorExplanation;
}

export function ErrorMessage({ errorExplanation }: ErrorMessageProps) {
    const [showDetails, setShowDetails] = React.useState(false);
    const [showSuggestions, setShowSuggestions] = React.useState(false);
    const [showTechnical, setShowTechnical] = React.useState(false);

    return (
        <div className="my-4">
            <Alert className="border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/20">
                <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-500" />
                <AlertTitle className="text-lg font-semibold text-foreground">Error Analysis</AlertTitle>
                <AlertDescription className="mt-2">
                    <div className="space-y-3">
                        {/* What Happened - Always visible */}
                        <div>
                            <p className="text-sm text-muted-foreground">{errorExplanation.what_happened}</p>
                        </div>

                        {/* Why It Happened - Collapsible */}
                        <div>
                            <button
                                onClick={() => setShowDetails(!showDetails)}
                                className="flex items-center gap-2 text-sm font-medium text-foreground hover:text-amber-600 dark:hover:text-amber-500 transition-colors focus:outline-none"
                            >
                                {showDetails ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                                <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-500" />
                                Why This Happened
                            </button>
                            {showDetails && (
                                <div className="mt-2 ml-6 space-y-2">
                                    <p className="text-sm text-muted-foreground">{errorExplanation.why_it_happened}</p>
                                    <div className="bg-muted/50 p-2 rounded-md border border-border">
                                        <p className="text-xs text-muted-foreground"><span className="font-medium">Attempted:</span> {errorExplanation.what_was_attempted}</p>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Alternative Suggestions - Collapsible */}
                        {errorExplanation.alternative_suggestions && errorExplanation.alternative_suggestions.length > 0 && (
                            <div>
                                <button
                                    onClick={() => setShowSuggestions(!showSuggestions)}
                                    className="flex items-center gap-2 text-sm font-medium text-foreground hover:text-amber-600 dark:hover:text-amber-500 transition-colors focus:outline-none"
                                >
                                    {showSuggestions ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                                    <Lightbulb className="h-4 w-4 text-amber-600 dark:text-amber-500" />
                                    Suggested Solutions ({errorExplanation.alternative_suggestions.length})
                                </button>
                                {showSuggestions && (
                                    <ul className="mt-2 ml-6 space-y-1.5">
                                        {errorExplanation.alternative_suggestions.map((suggestion, index) => (
                                            <li key={index} className="flex items-start gap-2 text-sm text-muted-foreground">
                                                <ArrowRight className="h-4 w-4 mt-0.5 flex-shrink-0 text-amber-600 dark:text-amber-500" />
                                                <span>{suggestion}</span>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        )}

                        {/* User Action Needed - Always visible, compact */}
                        <div className="bg-blue-50 dark:bg-blue-950/20 p-2.5 rounded-md border-l-4 border-blue-500">
                            <p className="text-sm text-muted-foreground"><span className="font-semibold text-foreground">Next Step:</span> {errorExplanation.user_action_needed}</p>
                        </div>

                        {/* Technical Details - Collapsible */}
                        {errorExplanation.technical_details && (
                            <div>
                                <button
                                    onClick={() => setShowTechnical(!showTechnical)}
                                    className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors focus:outline-none"
                                >
                                    {showTechnical ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                                    <span className="px-2 py-1 border border-border rounded bg-muted/50">
                                        {showTechnical ? 'Hide' : 'Show'} Technical Details
                                    </span>
                                </button>
                                {showTechnical && (
                                    <div className="mt-2 bg-muted p-2.5 rounded-md border border-border">
                                        <code className="text-xs text-muted-foreground break-all font-mono">
                                            {errorExplanation.technical_details}
                                        </code>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </AlertDescription>
            </Alert>
        </div>
    );
}
