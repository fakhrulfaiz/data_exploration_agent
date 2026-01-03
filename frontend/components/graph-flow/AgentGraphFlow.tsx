'use client'

import React, { useEffect, useState, useCallback } from 'react';
import { ReactFlow, Background, applyNodeChanges, applyEdgeChanges, Node, Edge, NodeChange, EdgeChange, addEdge, Connection, ConnectionMode } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { GraphStructure, NodeStatus } from '@/types/graph';
import CustomNode from './CustomNode';
import './reactflow-custom.css';

const nodeTypes = {
    custom: CustomNode,
};

interface AgentGraphFlowProps {
    threadId?: string;
    onNodeClick?: (nodeId: string) => void;
    className?: string;
    graphStructure?: GraphStructure | null;
}

const AgentGraphFlow: React.FC<AgentGraphFlowProps> = ({
    threadId,
    onNodeClick,
    className = '',
    graphStructure: preloadedGraphStructure
}) => {
    const [nodes, setNodes] = useState<Node[]>([]);
    const [edges, setEdges] = useState<Edge[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Load and convert graph data
    useEffect(() => {
        const loadGraph = async () => {
            try {
                setLoading(true);

                let graphData = preloadedGraphStructure;

                if (!graphData) {
                    const response = await fetch('/api/v1/graph/structure');
                    if (!response.ok) throw new Error('Failed to fetch graph structure');
                    const result = await response.json();
                    if (!result.success || !result.data) throw new Error('Invalid graph data');
                    graphData = result.data;
                }

                if (graphData) {
                    // Convert to React Flow format
                    const flowNodes: Node[] = graphData.nodes.map(node => ({
                        id: node.id,
                        position: node.position,
                        data: {
                            label: node.label,
                            status: node.status || 'pending',
                            nodeType: node.type || 'default',
                        },
                        type: 'custom',  // Use custom node with multiple handles
                    }));

                    const flowEdges: Edge[] = graphData.edges.map(edge => ({
                        id: edge.id,
                        source: edge.source,
                        target: edge.target,
                        type: edge.type || 'smoothstep',

                        // sourceHandle/targetHandle: 'top' | 'bottom' | 'left' | 'right'
                        sourceHandle: edge.sourceHandle,
                        targetHandle: edge.targetHandle,

                        // Style customization
                        // style: {
                        //   stroke: '#3b82f6',      // Edge color
                        //   strokeWidth: 3,          // Edge thickness
                        //   strokeDasharray: '5,5',  // Dashed line
                        // },

                        label: edge.label || undefined,
                        animated: edge.active || false,

                    }));

                    setNodes(flowNodes);
                    setEdges(flowEdges);
                }

                setLoading(false);
            } catch (err) {
                console.error('Error loading graph:', err);
                setError(err instanceof Error ? err.message : 'Failed to load graph');
                setLoading(false);
            }
        };

        loadGraph();
    }, [preloadedGraphStructure]);

    // Handle node changes (dragging, selection, etc.)
    const onNodesChange = useCallback(
        (changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
        []
    );

    const onEdgesChange = useCallback(
        (changes: EdgeChange[]) => setEdges((eds) => applyEdgeChanges(changes, eds)),
        []
    );

    // Handle node click
    const handleNodeClick = useCallback(
        (_event: React.MouseEvent, node: Node) => {
            onNodeClick?.(node.id);
        },
        [onNodeClick]
    );

    // Handle new edge connections (drag from one node to another)
    const onConnect = useCallback(
        (connection: Connection) => {
            console.log('New edge created:', connection);
            const edge = { ...connection, type: 'smoothstep' };
            setEdges((eds) => addEdge(edge, eds));
        },
        [setEdges]
    );

    // Use Ref to track active node synchronously (solves race conditions with rapid updates)
    const activeNodeRef = React.useRef<string | null>(null);

    // Update node status based on streaming events
    const updateNodeStatus = useCallback((nodeId: string, status: NodeStatus, previousNodeId?: string) => {
        console.log('[AgentGraphFlow] updateNodeStatus called:', {
            nodeId,
            status,
            previousNodeId,
            activeNodeRef_current: activeNodeRef.current
        });

        // Infer previous node from REF (synchronous source of truth)
        // This makes it independent of React render cycles
        const effectivePreviousId = previousNodeId || activeNodeRef.current;

        console.log('[AgentGraphFlow] effectivePreviousId:', effectivePreviousId);

        // Update the ref immediately for the NEXT call
        if (status === 'active') {
            activeNodeRef.current = nodeId;
            console.log('[AgentGraphFlow] Updated activeNodeRef to:', nodeId);
        }

        setNodes((nds) =>
            nds.map((node) => {
                // 1. Update the target node to the new status
                if (node.id === nodeId) {
                    console.log(`[AgentGraphFlow] Setting ${nodeId} to ${status}`);
                    return { ...node, data: { ...node.data, status } };
                }

                // 2. Complete the previous node if it's still marked as active
                // CRITICAL: Only complete if it's the effectivePreviousId AND currently active
                // Don't use OR (||) here - that would complete the wrong nodes!
                if (effectivePreviousId && node.id === effectivePreviousId && node.data.status === 'active') {
                    console.log(`[AgentGraphFlow] Completing previous node: ${node.id}`);
                    return { ...node, data: { ...node.data, status: 'completed' } };
                }

                return node;
            })
        );

        // Update edges: clear previous animations and set new one
        if (effectivePreviousId) {
            console.log(`[AgentGraphFlow] Animating edge: ${effectivePreviousId} -> ${nodeId}`);
            setEdges((eds) =>
                eds.map(edge => {
                    // Animate the edge connecting previous -> current
                    if (edge.source === effectivePreviousId && edge.target === nodeId) {
                        return { ...edge, animated: true };
                    }
                    // Clear animation from all OTHER edges (not the current one)
                    if (edge.animated && !(edge.source === effectivePreviousId && edge.target === nodeId)) {
                        return { ...edge, animated: false };
                    }
                    return edge;
                })
            );
        } else {
            console.log('[AgentGraphFlow] No effectivePreviousId, skipping edge animation');
        }
    }, []);

    // Expose update methods globally
    useEffect(() => {
        if (typeof window !== 'undefined') {
            (window as any).updateGraphNodeStatus = updateNodeStatus;
        }
    }, [updateNodeStatus]);

    // Expose graph data to window for save functionality
    useEffect(() => {
        (window as any).getCurrentGraphData = () => ({
            nodes: nodes.map(n => ({
                id: n.id,
                position: n.position,
                data: n.data,
                type: n.type
            })),
            edges: edges.map(e => ({
                id: e.id,
                source: e.source,
                target: e.target,
                sourceHandle: e.sourceHandle,
                targetHandle: e.targetHandle,
                type: e.type,
                label: e.label
            }))
        });

        return () => {
            delete (window as any).getCurrentGraphData;
        };
    }, [nodes, edges]);

    const [rfInstance, setRfInstance] = useState<any>(null);
    const containerRef = React.useRef<HTMLDivElement>(null);

    // Auto-fit on resize
    useEffect(() => {
        if (!rfInstance || !containerRef.current) return;

        const observer = new ResizeObserver(() => {
            window.requestAnimationFrame(() => {
                rfInstance.fitView({ padding: 0.2, duration: 200 });
            });
        });

        observer.observe(containerRef.current);

        return () => {
            observer.disconnect();
        };
    }, [rfInstance]);

    // Auto-fit when nodes/edges change or loading finishes
    useEffect(() => {
        if (rfInstance && !loading && nodes.length > 0) {
            // Include a small delay to ensure rendering is complete
            const timeout = setTimeout(() => {
                rfInstance.fitView({ padding: 0.2, duration: 400 });
            }, 100);
            return () => clearTimeout(timeout);
        }
    }, [rfInstance, loading, nodes.length, edges.length]);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-muted-foreground">Loading graph...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-destructive">Error: {error}</div>
            </div>
        );
    }

    return (
        <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={handleNodeClick}
                onInit={setRfInstance}
                nodeTypes={nodeTypes}
                connectionMode={ConnectionMode.Loose}
                fitView
                // Static View Props
                panOnDrag={false}
                zoomOnScroll={false}
                zoomOnPinch={false}
                zoomOnDoubleClick={false}
                nodesDraggable={true} // Keep nodes draggable as requested
                nodesConnectable={true}
                elementsSelectable={true}
                preventScrolling={false}
            >
                <Background />
            </ReactFlow>
        </div>
    );
};

export default AgentGraphFlow;
