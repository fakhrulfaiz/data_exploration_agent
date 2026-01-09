/**
 * Types for agent graph flow visualization
 */

export type NodeStatus = 'pending' | 'active' | 'completed' | 'error';
export type NodeType = 'entry' | 'end' | 'assistant' | 'entry_point' | 'planner' | 'executor' | 'tools' | 'explainer' | 'finalizer' | 'feedback' | 'node';
export type EdgeType = 'fixed' | 'conditional';

export interface GraphNode {
    id: string;
    label: string;
    type: NodeType;
    position: { x: number; y: number };
    status: NodeStatus;
    index: number;
}

export interface GraphEdge {
    id: string;
    source: string;
    target: string;
    type: string;  // Changed from EdgeType to string to support 'smoothstep', 'smart', 'default', etc.
    sourceHandle?: string;
    targetHandle?: string;
    label?: string | null;
    active: boolean;
}

export interface GraphStructure {
    nodes: GraphNode[];
    edges: GraphEdge[];
}

export interface GraphNodeEvent {
    node_id: string;
    status: NodeStatus;
    previous_node_id?: string | null;
    timestamp: string;
}
