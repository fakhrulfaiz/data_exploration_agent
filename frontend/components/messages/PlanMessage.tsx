'use client';

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { markdownComponents } from '../../utils/markdownComponents';
import { ChevronDown, ChevronRight, Circle } from 'lucide-react';

interface PlanItem {
    number: number;
    toolName: string;
    description: string;
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

    // Parse plan text to extract numbered items
    const parsePlan = (planText: string): { intro: string; items: PlanItem[]; outro: string } => {
        const lines = planText.split('\n');
        const items: PlanItem[] = [];
        const introLines: string[] = [];
        const outroLines: string[] = [];
        let inItems = false;
        let afterItems = false;

        // Regex to match numbered plan items: "1. tool_name: description"
        const itemRegex = /^(\d+)\.\s+(\w+):\s+(.+)$/;

        for (const line of lines) {
            const match = line.match(itemRegex);
            if (match) {
                inItems = true;
                items.push({
                    number: parseInt(match[1], 10),
                    toolName: match[2],
                    description: match[3]
                });
            } else if (!inItems && line.trim()) {
                // Lines before first numbered item
                introLines.push(line);
            } else if (inItems && line.trim()) {
                // Lines after last numbered item
                afterItems = true;
                outroLines.push(line);
            } else if (afterItems) {
                outroLines.push(line);
            }
        }

        return {
            intro: introLines.join('\n').trim(),
            items,
            outro: outroLines.join('\n').trim()
        };
    };

    const { intro, items, outro } = parsePlan(plan);

    return (
        <div className="plan-message">
            {/* Intro text (if any) */}
            {intro && (
                <div className="mb-3 prose prose-sm dark:prose-invert max-w-none">
                    <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
                        {intro}
                    </ReactMarkdown>
                </div>
            )}

            {/* Plan items in single expandable card */}
            {items.length > 0 && (
                <div>
                    {/* Clickable header outside card */}
                    <button
                        onClick={() => setIsExpanded(!isExpanded)}
                        className="mb-2 flex items-center gap-2 hover:opacity-80 transition-opacity"
                    >
                        {isExpanded ? (
                            <ChevronDown className="w-4 h-4 text-muted-foreground" />
                        ) : (
                            <ChevronRight className="w-4 h-4 text-muted-foreground" />
                        )}
                        <span className="font-semibold text-foreground">
                            Execution Plan
                        </span>
                    </button>

                    {/* Card with list items only */}
                    {isExpanded && (
                        <div className="border border-border rounded-lg bg-background shadow-sm px-4 py-3">
                            <ul className="space-y-3">
                                {items.map((item) => (
                                    <li key={item.number} className="flex gap-3 items-start">
                                        <Circle className="w-2 h-2 fill-current text-primary shrink-0 mt-2" />
                                        <div className="flex-1">
                                            <span className="font-medium text-foreground">
                                                {item.toolName}:
                                            </span>
                                            <span className="text-muted-foreground ml-1">
                                                {item.description}
                                            </span>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            )}

            {/* Outro text (if any) */}
            {outro && (
                <div className="mt-3 prose prose-sm dark:prose-invert max-w-none">
                    <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
                        {outro}
                    </ReactMarkdown>
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
