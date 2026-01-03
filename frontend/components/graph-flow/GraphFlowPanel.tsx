'use client'

import React, { useState, useEffect, useCallback } from 'react';
import AgentGraphFlow from './AgentGraphFlow';
import { GraphNodeEvent, NodeStatus, GraphStructure } from '@/types/graph';
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { X, Save, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface GraphFlowPanelProps {
    open: boolean;
    onClose: () => void;
    threadId?: string;
    graphStructure?: GraphStructure | null;
    initialWidthPx?: number;
    minWidthPx?: number;
    maxWidthPx?: number;
}

const GraphFlowPanel: React.FC<GraphFlowPanelProps> = ({
    open,
    onClose,
    threadId,
    graphStructure,
    initialWidthPx = 800,
    minWidthPx = 600,
    maxWidthPx = 1200,
}) => {
    const [graphNodeHistory, setGraphNodeHistory] = useState<Map<string, NodeStatus>>(new Map());
    const [saveMessage, setSaveMessage] = useState<string>('');

    const handleSaveLayout = () => {
        // Get current graph state from AgentGraphFlow via window
        const graphData = (window as any).getCurrentGraphData?.();
        if (graphData) {
            localStorage.setItem('custom-graph-layout', JSON.stringify(graphData));
            setSaveMessage('Layout saved!');
            setTimeout(() => setSaveMessage(''), 2000);
        }
    };

    const handleResetLayout = () => {
        localStorage.removeItem('custom-graph-layout');
        setSaveMessage('Layout reset!');
        setTimeout(() => setSaveMessage(''), 2000);
        window.location.reload(); // Reload to get default layout
    };

    const getResponsiveWidth = () => {
        const screenWidth = typeof window !== 'undefined' ? window.innerWidth : initialWidthPx;
        if (screenWidth <= 768) {
            return Math.min(screenWidth, maxWidthPx);
        } else if (screenWidth <= 1024) {
            return Math.min(screenWidth * 0.8, initialWidthPx);
        }
        return initialWidthPx;
    };

    const getIsMobile = () => (typeof window !== 'undefined' ? window.innerWidth <= 768 : false);

    const [width, setWidth] = useState<number>(initialWidthPx);
    const [isMobile, setIsMobile] = useState<boolean>(false);

    useEffect(() => {
        setWidth(getResponsiveWidth());
        setIsMobile(getIsMobile());
    }, []);

    // Handle graph node events from streaming
    const handleGraphNodeEvent = useCallback((event: GraphNodeEvent) => {
        setGraphNodeHistory(prev => {
            const updated = new Map(prev);
            updated.set(event.node_id, event.status);
            return updated;
        });

        // Update node status in the graph visualization
        if (typeof window !== 'undefined' && (window as any).updateGraphNodeStatus) {
            (window as any).updateGraphNodeStatus(event.node_id, event.status);
        }

        // Mark previous node as completed when moving to next node
        if (event.status === 'active') {
            const prevNodes = Array.from(graphNodeHistory.entries());
            const lastActiveNode = prevNodes.find(([_, status]) => status === 'active');

            if (lastActiveNode && lastActiveNode[0] !== event.node_id) {
                if (typeof window !== 'undefined' && (window as any).updateGraphNodeStatus) {
                    (window as any).updateGraphNodeStatus(lastActiveNode[0], 'completed');
                }
            }
        }
    }, [graphNodeHistory]);

    // Expose handler for parent component
    useEffect(() => {
        if (typeof window !== 'undefined') {
            (window as any).handleGraphNodeEvent = handleGraphNodeEvent;
        }

        return () => {
            if (typeof window !== 'undefined') {
                delete (window as any).handleGraphNodeEvent;
            }
        };
    }, [handleGraphNodeEvent]);

    return (
        <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
            <SheetContent
                side="right"
                hideCloseButton
                className="p-0 h-full max-w-full w-full shadow-xl border-l border-gray-200 dark:border-neutral-700 bg-white dark:bg-neutral-900"
                style={{
                    width: isMobile ? '100%' : width,
                    minWidth: isMobile ? undefined : minWidthPx,
                    maxWidth: isMobile ? '100%' : maxWidthPx,
                }}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-neutral-700 bg-gray-50 dark:bg-neutral-900">
                    <h3 className="font-semibold text-gray-900 dark:text-white">Agent Execution Flow</h3>
                    <div className="flex items-center gap-2">
                        {saveMessage && <span className="text-sm text-green-600 dark:text-green-400">{saveMessage}</span>}
                        <Button onClick={handleSaveLayout} size="sm" variant="outline">
                            <Save className="h-4 w-4 mr-1" />
                            Save
                        </Button>
                        <Button onClick={handleResetLayout} size="sm" variant="outline">
                            <RotateCcw className="h-4 w-4 mr-1" />
                            Reset
                        </Button>
                        <button
                            onClick={onClose}
                            className="px-3 py-2 rounded bg-gray-200 dark:bg-neutral-700 hover:bg-gray-300 dark:hover:bg-neutral-600 text-gray-800 dark:text-white text-sm"
                            aria-label="Close panel"
                        >
                            Close
                        </button>
                    </div>
                </div>

                {/* Graph Content */}
                <div className="h-[calc(100%-56px)] overflow-hidden">
                    <AgentGraphFlow
                        threadId={threadId}
                        graphStructure={graphStructure}
                    />
                </div>
            </SheetContent>
        </Sheet>
    );
};

export default GraphFlowPanel;
