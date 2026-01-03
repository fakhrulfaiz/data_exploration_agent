'use client'

import React, { useEffect, useState, useCallback } from 'react';
import { ReactFlow, Background, Controls, MiniMap, applyNodeChanges, applyEdgeChanges, Node, Edge, NodeChange, EdgeChange, addEdge, Connection, ConnectionMode } from '@xyflow/react';
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

                        // 🎨 EDGE CUSTOMIZATION OPTIONS:
                        // type: 'smart' (pathfinding) | 'step' | 'straight' | 'default' | 'smoothstep'
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

                        // markerEnd: {
                        //   type: MarkerType.ArrowClosed,
                        //   color: '#3b82f6',
                        // },
                    }));

                    // 🔍 DEBUG: Log full graph structure to console
                    console.group('📊 Graph Structure Loaded');
                    console.log('Nodes:', flowNodes.length);
                    console.table(flowNodes.map(n => ({ id: n.id, label: n.data.label, x: n.position.x, y: n.position.y })));
                    console.log('Edges:', flowEdges.length);
                    console.table(flowEdges.map(e => ({ id: e.id, from: e.source, to: e.target, type: e.type })));
                    console.log('Full Graph Data:', { nodes: flowNodes, edges: flowEdges });
                    console.groupEnd();

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

    // Update node status based on streaming events
    const updateNodeStatus = useCallback((nodeId: string, status: NodeStatus) => {
        setNodes((nds) =>
            nds.map((node) =>
                node.id === nodeId
                    ? { ...node, data: { ...node.data, status } }
                    : node
            )
        );
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
        <div style={{ width: '100%', height: '100%' }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={handleNodeClick}
                nodeTypes={nodeTypes}
                connectionMode={ConnectionMode.Loose}
                fitView
            >
                <Background />
                <Controls />
                <MiniMap />
            </ReactFlow>
        </div>
    );
};

export default AgentGraphFlow;
