'use client'

import React, { useState, useEffect, useCallback } from 'react';
import AgentGraphFlow from './AgentGraphFlow';
import { GraphNodeEvent, NodeStatus, GraphStructure } from '@/types/graph';
import { X, Save, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface GraphFlowPanelProps {
    open: boolean;
    onClose: () => void;
    threadId?: string;
    graphStructure?: GraphStructure | null;
}

const GraphFlowPanel: React.FC<GraphFlowPanelProps> = ({
    open,
    onClose,
    threadId,
    graphStructure,
}) => {
    const [graphNodeHistory, setGraphNodeHistory] = useState<Map<string, NodeStatus>>(new Map());
    const [saveMessage, setSaveMessage] = useState<string>('');

    const handleSaveLayout = () => {
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
        window.location.reload();
    };

    const handleGraphNodeEvent = useCallback((event: GraphNodeEvent) => {
        console.log('[GraphFlowPanel] Received event:', JSON.stringify(event, null, 2));

        setGraphNodeHistory(prev => {
            const updated = new Map(prev);
            updated.set(event.node_id, event.status);
            return updated;
        });

        // Pass all three parameters including previous_node_id for edge inference
        // updateNodeStatus already handles completing the previous node, so we don't need to do it here
        if (typeof window !== 'undefined' && (window as any).updateGraphNodeStatus) {
            console.log('[GraphFlowPanel] Calling updateGraphNodeStatus with:', {
                node_id: event.node_id,
                status: event.status,
                previous_node_id: event.previous_node_id
            });
            (window as any).updateGraphNodeStatus(
                event.node_id,
                event.status,
                event.previous_node_id  // CRITICAL: This enables edge animations!
            );
        } else {
            console.warn('[GraphFlowPanel] updateGraphNodeStatus not found on window!');
        }
    }, [graphNodeHistory]);

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

    if (!open) return null;

    return (
        <div className="flex flex-col h-full w-full">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-border bg-muted/50">
                <h3 className="font-semibold">Agent Execution Flow</h3>
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
                    <Button onClick={onClose} size="sm" variant="ghost">
                        <X className="h-4 w-4" />
                    </Button>
                </div>
            </div>

            {/* Graph Content */}
            <div className="flex-1 overflow-hidden w-full">
                <AgentGraphFlow
                    threadId={threadId}
                    graphStructure={graphStructure}
                />
            </div>
        </div>
    );
};

export default GraphFlowPanel;
