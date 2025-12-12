'use client'

import React from 'react';

interface ExplorerMessageProps {
  data?: any;
  checkpointId?: string;
  onOpenExplorer?: () => void;
}

export const ExplorerMessage: React.FC<ExplorerMessageProps> = ({
  data,
  checkpointId,
  onOpenExplorer
}) => {
  const getSummary = () => {
    if (!data) return 'Click to view analysis details';

    const parts = [] as string[];

    if (data.steps && data.steps.length > 0) {
      parts.push(`${data.steps.length} step${data.steps.length !== 1 ? 's' : ''} executed`);
    }

    if (data.overall_confidence) {
      parts.push(`${(data.overall_confidence * 100).toFixed(0)}% confidence`);
    }

    if (data.run_status) {
      parts.push(`${data.run_status}`);
    }

    return parts.length > 0 ? parts.join(' • ') : 'Click to view analysis details';
  };

  const getUserQuestion = () => {
    if (data?.query) {
      return data.query;
    }
    return 'Analysis Complete';
  };

  return (
    <div
      onClick={onOpenExplorer}
      className="border border-border rounded-lg p-4 bg-background hover:bg-accent cursor-pointer transition-colors"
    >
      <div className="font-medium text-foreground mb-2 max-w-full">
        <span className="text-primary text-sm font-normal">Question: </span>
        <span className="truncate block">{getUserQuestion()}</span>
      </div>

      <div className="text-sm text-muted-foreground">
        {getSummary()}
      </div>
    </div>
  );
};


