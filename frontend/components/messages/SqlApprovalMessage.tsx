import React, { useState } from 'react';
import { ContentBlock } from '@/types/chat';

interface SqlApprovalMessageProps {
    data: {
        sql: string;
        type: string;
        tool_call_id?: string;
    };
    onApprove?: () => void;
    onReject?: () => void;
    onEdit?: (newSql: string) => void;
}

export const SqlApprovalMessage: React.FC<SqlApprovalMessageProps> = ({
    data,
    onApprove,
    onReject,
    onEdit
}) => {
    const [isEditing, setIsEditing] = useState(false);
    const [editedSql, setEditedSql] = useState(data.sql);

    const handleEditConfirm = () => {
        if (onEdit) {
            onEdit(editedSql);
            setIsEditing(false);
        }
    };

    return (
        <div className="bg-muted/50 rounded-lg p-4 border border-border">
            <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-foreground">SQL Query Approval</h3>
                {!isEditing && (
                    <div className="flex gap-2">
                        <button
                            onClick={() => setIsEditing(true)}
                            className="px-3 py-1 text-xs font-medium bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                        >
                            Edit
                        </button>
                    </div>
                )}
            </div>

            {isEditing ? (
                <div className="space-y-2">
                    <textarea
                        value={editedSql}
                        onChange={(e) => setEditedSql(e.target.value)}
                        className="w-full h-32 p-2 font-mono text-sm bg-background border border-input rounded-md focus:ring-2 focus:ring-ring"
                    />
                    <div className="flex gap-2 justify-end">
                        <button
                            onClick={() => setIsEditing(false)}
                            className="px-3 py-1 text-xs font-medium text-muted-foreground hover:bg-muted"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleEditConfirm}
                            className="px-3 py-1 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90"
                        >
                            Update & Approve
                        </button>
                    </div>
                </div>
            ) : (
                <div className="rounded overflow-hidden my-2 bg-zinc-900 p-4">
                    <pre className="m-0 text-sm font-mono text-zinc-50 whitespace-pre-wrap break-all">
                        <code>{data.sql}</code>
                    </pre>
                </div>
            )}

            {
                !isEditing && (
                    <div className="flex gap-2 mt-3 justify-end">
                        <button
                            onClick={onReject}
                            className="px-4 py-2 text-sm font-medium bg-red-100 text-red-700 rounded-md hover:bg-red-200 transition-colors"
                        >
                            Reject
                        </button>
                        <button
                            onClick={onApprove}
                            className="px-4 py-2 text-sm font-medium bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors"
                        >
                            Approve Execution
                        </button>
                    </div>
                )
            }
        </div >
    );
};
