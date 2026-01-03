'use client'

import React, { memo } from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';

interface CustomNodeData {
    label: string;
    status: 'pending' | 'active' | 'completed' | 'error';
    nodeType: string;
}

const CustomNode = ({ data }: NodeProps) => {
    const nodeData = data as unknown as CustomNodeData;

    return (
        <div className={`custom-graph-node ${nodeData.status || ''}`}>
            {/* 
        🎯 CUSTOM HANDLE POSITIONING
        You can add handles anywhere with custom styles!
        
        Position options: Position.Top, Position.Bottom, Position.Left, Position.Right
        
        For custom positions, use style prop:
        style={{ top: '25%', left: 0 }}  - 25% from top on left edge
        style={{ top: '75%', left: 0 }}  - 75% from top on left edge
        style={{ top: 0, left: '30%' }}  - 30% from left on top edge
      */}

            {/* Top Anchor (Universal Source) */}
            <Handle
                type="source"
                position={Position.Top}
                id="top"
                style={{ background: '#555' }}
            />

            {/* Left Anchors (Universal Source) */}
            {/* left-top */}
            <Handle
                type="source"
                position={Position.Left}
                id="left-top"
                style={{ top: '25%', background: '#555' }}
            />

            {/* left-bottom */}
            <Handle
                type="source"
                position={Position.Left}
                id="left-bottom"
                style={{ top: '75%', background: '#555' }}
            />

            <div className="node-label">{nodeData.label}</div>

            {/* Bottom Anchor (Universal Source) */}
            <Handle
                type="source"
                position={Position.Bottom}
                id="bottom"
                style={{ background: '#555' }}
            />

            {/* Right Anchors (Universal Source) */}
            {/* right-top */}
            <Handle
                type="source"
                position={Position.Right}
                id="right-top"
                style={{ top: '25%', background: '#555' }}
            />

            {/* right-bottom */}
            <Handle
                type="source"
                position={Position.Right}
                id="right-bottom"
                style={{ top: '75%', background: '#555' }}
            />
        </div>
    );
};

export default memo(CustomNode);
