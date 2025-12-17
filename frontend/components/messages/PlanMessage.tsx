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
}

export const PlanMessage: React.FC<PlanMessageProps> = ({ plan }) => {
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
        </div>
    );
};
