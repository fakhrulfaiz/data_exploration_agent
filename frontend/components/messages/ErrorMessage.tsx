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
    const [isOpen, setIsOpen] = React.useState(false);

    return (
        <div className="my-4">
            <Alert className="border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/20">
                <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-500" />
                <AlertTitle className="text-lg font-semibold text-foreground">Something Went Wrong</AlertTitle>
                <AlertDescription className="mt-2">
                    <div className="space-y-4">
                        {/* What Happened */}
                        <div>
                            <h4 className="font-medium text-foreground mb-1">What Happened</h4>
                            <p className="text-sm text-muted-foreground">{errorExplanation.what_happened}</p>
                        </div>

                        {/* Why It Happened */}
                        <div>
                            <h4 className="font-medium text-foreground mb-1 flex items-center gap-2">
                                <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-500" />
                                Why It Happened
                            </h4>
                            <p className="text-sm text-muted-foreground">{errorExplanation.why_it_happened}</p>
                        </div>

                        {/* What Was Attempted */}
                        <div className="bg-muted/50 p-3 rounded-md border border-border">
                            <h4 className="font-medium text-foreground mb-1 text-sm">What We Were Trying To Do</h4>
                            <p className="text-sm text-muted-foreground">{errorExplanation.what_was_attempted}</p>
                        </div>

                        {/* Alternative Suggestions */}
                        {errorExplanation.alternative_suggestions && errorExplanation.alternative_suggestions.length > 0 && (
                            <div>
                                <h4 className="font-medium text-foreground mb-2 flex items-center gap-2">
                                    <Lightbulb className="h-4 w-4 text-amber-600 dark:text-amber-500" />
                                    Suggested Alternatives
                                </h4>
                                <ul className="space-y-2">
                                    {errorExplanation.alternative_suggestions.map((suggestion, index) => (
                                        <li key={index} className="flex items-start gap-2 text-sm text-muted-foreground">
                                            <ArrowRight className="h-4 w-4 mt-0.5 flex-shrink-0 text-amber-600 dark:text-amber-500" />
                                            <span>{suggestion}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {/* User Action Needed */}
                        <div className="bg-blue-50 dark:bg-blue-950/20 p-3 rounded-md border-l-4 border-blue-500">
                            <h4 className="font-semibold text-foreground mb-1 text-sm">What You Should Do Next</h4>
                            <p className="text-sm text-muted-foreground">{errorExplanation.user_action_needed}</p>
                        </div>

                        {/* Technical Details (Collapsible) */}
                        {errorExplanation.technical_details && (
                            <div>
                                <button
                                    onClick={() => setIsOpen(!isOpen)}
                                    className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors focus:outline-none"
                                >
                                    {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                                    <span className="px-2 py-1 border border-border rounded text-xs bg-muted/50">
                                        {isOpen ? 'Hide' : 'Show'} Technical Details
                                    </span>
                                </button>
                                {isOpen && (
                                    <div className="mt-2 bg-muted p-3 rounded-md border border-border">
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
