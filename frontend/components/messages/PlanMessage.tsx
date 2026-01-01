'use client';

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { markdownComponents } from '../../utils/markdownComponents';
import { ChevronDown, ChevronRight, ListOrdered, Wrench } from 'lucide-react';

interface ToolOption {
    name: string;
    description: string;
}

interface PlanStep {
    stepNumber: number;
    title: string;
    toolOptions: ToolOption[];
    requires?: string;
}

interface ParsedPlan {
    intent?: {
        main_intent: string;
        sub_intents: string[];
    };
    strategy: string;
    steps: PlanStep[];
}

interface IntentUnderstanding {
    main_intent: string;
    sub_intents: string[];
}

interface PlanMessageProps {
    plan: string;
    // Approval props (optional - for HITL)
    needsApproval?: boolean;
    onApprove?: () => void;
    onReject?: () => void;
    disabled?: boolean;
}

export const PlanMessage: React.FC<PlanMessageProps> = ({
    plan,
    needsApproval = false,
    onApprove,
    onReject,
    disabled = false
}) => {
    const [isExpanded, setIsExpanded] = useState(true);

    // Parse the new plan format
    const parsePlan = (planText: string): ParsedPlan => {
        const lines = planText.split('\n');
        let intentMainIntent: string | null = null;
        const intentSubIntents: string[] = [];
        let strategy = '';
        const steps: PlanStep[] = [];
        let currentStep: PlanStep | null = null;
        let inToolOptions = false;
        let inRequires = false;
        let inIntent = false;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            // Check for Intent header
            if (line.startsWith('**Intent**:')) {
                intentMainIntent = line.replace('**Intent**:', '').trim();
                inIntent = true;
                continue;
            }

            // Check for sub-intents (bullet points after Intent)
            if (inIntent && line.trim().startsWith('•')) {
                intentSubIntents.push(line.trim().substring(1).trim());
                continue;
            }

            // Check for Strategy (ends intent section)
            if (line.startsWith('**Strategy**:')) {
                strategy = line.replace('**Strategy**:', '').trim();
                inIntent = false;
                continue;
            }

            // Empty line ends intent section
            if (inIntent && line.trim() === '') {
                inIntent = false;
                continue;
            }

            // Check for Step headers (e.g., **Step 1**: ...)
            const stepMatch = line.match(/^\*\*Step (\d+)\*\*:\s*(.+)$/);
            if (stepMatch) {
                // Save previous step if exists
                if (currentStep) {
                    steps.push(currentStep);
                }

                currentStep = {
                    stepNumber: parseInt(stepMatch[1], 10),
                    title: stepMatch[2].trim(),
                    toolOptions: []
                };
                inToolOptions = false;
                inRequires = false;
                continue;
            }

            // Check for Tool Options header
            if (line.trim() === 'Tool Options:' && currentStep) {
                inToolOptions = true;
                inRequires = false;
                continue;
            }

            // Parse tool options (numbered list items)
            if (inToolOptions && currentStep) {
                const toolMatch = line.match(/^\s+(\d+)\.\s+(.+?):\s*(.+)$/);
                if (toolMatch) {
                    currentStep.toolOptions.push({
                        name: toolMatch[2].trim(),
                        description: toolMatch[3].trim()
                    });
                    continue;
                }
            }

            // Check for Requires
            if (line.trim().startsWith('Requires:') && currentStep) {
                currentStep.requires = line.replace('Requires:', '').trim();
                inToolOptions = false;
                inRequires = true;
                continue;
            }
        }

        // Don't forget the last step
        if (currentStep) {
            steps.push(currentStep);
        }

        // Build intent object if we found intent data
        const parsedIntent = intentMainIntent ? {
            main_intent: intentMainIntent,
            sub_intents: intentSubIntents
        } : undefined;

        return { intent: parsedIntent, strategy, steps };
    };

    const { intent: parsedIntent, strategy, steps } = parsePlan(plan);

    return (
        <div className="plan-message">
            {/* Intent section - minimal, above strategy */}
            {parsedIntent && (
                <div className="mb-4 text-foreground">
                    {/* Main Intent - simple text */}
                    <p className="mb-2">
                        <span className="font-medium">Intent: </span>
                        {parsedIntent.main_intent}
                    </p>

                    {/* Sub-Intents - simple list, no borders */}
                    {parsedIntent.sub_intents && parsedIntent.sub_intents.length > 0 && (
                        <div className="ml-4 text-sm text-muted-foreground space-y-0.5">
                            {parsedIntent.sub_intents.map((subIntent: string, idx: number) => (
                                <div key={idx}>• {subIntent}</div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Strategy header */}
            {strategy && (
                <div className="mb-4">
                    <div className="flex items-center gap-2 mb-2">
                        <ListOrdered className="w-4 h-4 text-primary" />
                        <span className="font-semibold text-sm text-muted-foreground uppercase tracking-wide">Strategy</span>
                    </div>
                    <p className="text-foreground">{strategy}</p>
                </div>
            )}

            {/* Execution Plan steps */}
            {steps.length > 0 && (
                <div>
                    {/* Clickable header */}
                    <button
                        onClick={() => setIsExpanded(!isExpanded)}
                        className="mb-3 flex items-center gap-2 hover:opacity-80 transition-opacity"
                    >
                        {isExpanded ? (
                            <ChevronDown className="w-4 h-4 text-muted-foreground" />
                        ) : (
                            <ChevronRight className="w-4 h-4 text-muted-foreground" />
                        )}
                        <span className="font-semibold text-foreground">
                            Execution Plan ({steps.length} {steps.length === 1 ? 'step' : 'steps'})
                        </span>
                    </button>

                    {/* Steps list */}
                    {isExpanded && (
                        <div className="space-y-3">
                            {steps.map((step) => (
                                <div
                                    key={step.stepNumber}
                                    className="border border-border rounded-lg bg-background shadow-sm overflow-hidden"
                                >
                                    {/* Step header */}
                                    <div className="px-4 py-3 bg-accent/50">
                                        <div className="flex items-start gap-2">
                                            <span className="flex-shrink-0 flex items-center justify-center w-6 h-6 rounded-full bg-primary text-primary-foreground text-xs font-bold">
                                                {step.stepNumber}
                                            </span>
                                            <div className="flex-1 min-w-0">
                                                <p className="font-medium text-foreground">{step.title}</p>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Tool options */}
                                    {step.toolOptions.length > 0 && (
                                        <div className="px-4 py-3 border-t border-border">
                                            <div className="flex items-center gap-2 mb-2">
                                                <Wrench className="w-3.5 h-3.5 text-muted-foreground" />
                                                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                                                    Tool Options
                                                </span>
                                            </div>
                                            <ul className="space-y-2">
                                                {step.toolOptions.map((tool, idx) => (
                                                    <li key={idx} className="flex gap-2 items-start text-sm">
                                                        <span className="flex-shrink-0 text-muted-foreground font-medium">
                                                            {idx + 1}.
                                                        </span>
                                                        <div className="flex-1 min-w-0">
                                                            <span className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
                                                                {tool.name}
                                                            </span>
                                                            <span className="text-muted-foreground ml-2">
                                                                {tool.description}
                                                            </span>
                                                        </div>
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}

                                    {/* Requirements */}
                                    {step.requires && (
                                        <div className="px-4 py-2 bg-muted/50 text-xs text-muted-foreground border-t border-border">
                                            <span className="font-semibold">Requires:</span> {step.requires}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Approval buttons (same style as ToolCallMessage) */}
            {needsApproval && (onApprove || onReject) && (
                <div className="mt-4 flex gap-2">
                    {onApprove && (
                        <button
                            onClick={onApprove}
                            disabled={disabled}
                            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            Approve
                        </button>
                    )}
                    {onReject && (
                        <button
                            onClick={onReject}
                            disabled={disabled}
                            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 border border-input bg-background rounded-md hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                            Reject
                        </button>
                    )}
                </div>
            )}
        </div>
    );
};
