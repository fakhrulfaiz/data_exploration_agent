'use client';

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { markdownComponents } from '../../utils/markdownComponents';
import { ChevronDown, ChevronRight, ListOrdered, Wrench, AlertCircle } from 'lucide-react';

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

const PlanStepItem: React.FC<{ step: PlanStep; isLast: boolean }> = ({ step, isLast }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    return (
        <div className={`flex flex-col ${!isLast ? 'border-b border-border' : ''}`}>
             {/* Clickable Header Row */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="flex items-start gap-3 px-4 py-3 w-full text-left hover:bg-muted/30 transition-colors group"
            >
                {/* Chevron indicator */}
                <span className="mt-0.5 text-muted-foreground/50 group-hover:text-muted-foreground transition-colors">
                    {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </span>

                {/* Step Content */}
                <div className="flex-1 min-w-0 flex gap-3">
                    <span className="flex-shrink-0 flex items-center justify-center w-6 h-6 rounded-md bg-muted text-muted-foreground text-xs font-mono font-medium">
                        {step.stepNumber}
                    </span>
                    <p className="text-sm font-medium text-foreground pt-0.5">{step.title}</p>
                </div>
            </button>

            {/* Collapsible Details */}
            {isExpanded && (
                <div className="px-4 pb-3 pl-12 mt-2 space-y-3 animation-fade-in">
                    {/* Tool options */}
                    {step.toolOptions.length > 0 && (
                        <div className="bg-muted/30 rounded-md p-3 border border-border/50">
                            <div className="flex items-center gap-2 mb-2">
                                <Wrench className="w-3.5 h-3.5 text-muted-foreground" />
                                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
                                    Suggested Tool Options
                                </span>
                            </div>
                            <ul className="space-y-1.5">
                                {step.toolOptions.map((tool, idx) => (
                                    <li key={idx} className="flex gap-2 items-start text-xs">
                                        <span className="font-mono text-[10px] bg-background border border-border px-1.5 py-0.5 rounded text-foreground/80">
                                            {tool.name}
                                        </span>
                                        <span className="text-muted-foreground">
                                            {tool.description}
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {/* Requirements */}
                    {step.requires && (
                        <div className="flex gap-2 text-xs text-muted-foreground bg-amber-500/5 border border-amber-500/20 p-2.5 rounded-md">
                            <AlertCircle className="w-3.5 h-3.5 text-amber-600/70 mt-0.5 flex-shrink-0" />
                            <div>
                                <span className="font-medium text-amber-700/80 mr-1">Requires:</span>
                                {step.requires}
                            </div>
                        </div>
                    )}
                    
                    {/* Fallback if no details */}
                    {!step.requires && step.toolOptions.length === 0 && (
                        <p className="text-xs text-muted-foreground italic pl-1">No additional details for this step.</p>
                    )}
                </div>
            )}
        </div>
    );
};

export const PlanMessage: React.FC<PlanMessageProps> = ({
    plan,
    needsApproval = false,
    onApprove,
    onReject,
    disabled = false
}) => {
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
            const trimmedLine = line.trim();

            // Check for Intent header
            if (trimmedLine.startsWith('**Intent**:')) {
                intentMainIntent = trimmedLine.substring(11).trim();
                inIntent = true;
                continue;
            }

            // Check for sub-intents (bullet points after Intent)
            if (inIntent && trimmedLine.startsWith('•')) {
                intentSubIntents.push(trimmedLine.substring(1).trim());
                continue;
            }

            // Check for Strategy (ends intent section)
            if (trimmedLine.startsWith('**Strategy**:')) {
                strategy = trimmedLine.substring(13).trim();
                inIntent = false;
                continue;
            }

            // Empty line ends intent section
            if (inIntent && trimmedLine === '') {
                inIntent = false;
                continue;
            }

            // Check for Step headers (e.g., **Step 1**: ...)
            const stepMatch = line.match(/^\s*\*\*Step (\d+)\*\*:\s*(.+)$/);
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
            if (trimmedLine === 'Tool Options:' && currentStep) {
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
            if (trimmedLine.startsWith('Requires:') && currentStep) {
                currentStep.requires = trimmedLine.substring(9).trim();
                inToolOptions = false;
                inRequires = true;
                continue;
            }
        }

        // Don't forget the last step
        if (currentStep) {
            steps.push(currentStep);
        }

        const parsedIntent = intentMainIntent ? {
            main_intent: intentMainIntent,
            sub_intents: intentSubIntents
        } : undefined;

        return { intent: parsedIntent, strategy, steps };
    };

    const { strategy, steps } = parsePlan(plan);

    return (
        <div className="plan-message">
            {/* Strategy header */}
            {strategy && (
                <div className="mb-4">
                    <div className="flex items-center gap-2 mb-2">
                        <ListOrdered className="w-4 h-4 text-primary" />
                        <span className="font-semibold text-sm text-muted-foreground uppercase tracking-wide">Strategy</span>
                    </div>
                    <p className="text-foreground text-sm">{strategy}</p>
                </div>
            )}

            {/* Execution Plan steps */}
            {steps.length > 0 && (
                <div className="mb-4">
                    <div className="flex items-center gap-2 mb-2">
                        <span className="font-semibold text-sm text-foreground">Execution Plan</span>
                        <span className="text-xs text-muted-foreground">({steps.length} steps)</span>
                    </div>
                    
                    {/* Unified Card Container */}
                    <div className="border border-border rounded-lg bg-background shadow-sm overflow-hidden">
                        {steps.map((step, index) => (
                            <PlanStepItem 
                                key={step.stepNumber} 
                                step={step} 
                                isLast={index === steps.length - 1} 
                            />
                        ))}
                    </div>
                </div>
            )}

            {/* Approval buttons */}
            {needsApproval && (onApprove || onReject) && (
                <div className="mt-4 flex gap-2">
                    {onApprove && (
                        <button
                            onClick={onApprove}
                            disabled={disabled}
                            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            Approve Plan
                        </button>
                    )}
                    {onReject && (
                        <button
                            onClick={onReject}
                            disabled={disabled}
                            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 border border-input bg-background rounded-md hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                            Reject Plan
                        </button>
                    )}
                </div>
            )}
        </div>
    );
};
