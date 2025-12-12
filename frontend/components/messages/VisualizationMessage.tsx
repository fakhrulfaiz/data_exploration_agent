'use client'

import React from 'react';

interface VisualizationMessageProps {
  charts?: any[];
  checkpointId?: string;
  onOpenVisualization?: () => void;
}

export const VisualizationMessage: React.FC<VisualizationMessageProps> = ({
  charts,
  checkpointId,
  onOpenVisualization,
}) => {
  const getSummary = () => {
    const count = Array.isArray(charts) ? charts.length : 0;
    if (count === 0) return 'Click to view visualization';
    const types = (charts || [])
      .map((c: any) => c?.type)
      .filter(Boolean)
      .slice(0, 3)
      .join(', ');
    return `${count} chart${count !== 1 ? 's' : ''}${types ? ` • ${types}` : ''}`;
  };

  const getTitle = () => {
    return 'Visualization Ready';
  };

  return (
    <div
      onClick={onOpenVisualization}
      className="border border-border rounded-lg p-4 bg-background hover:bg-accent cursor-pointer transition-colors"
    >
      <div className="font-medium text-foreground mb-2">
        <span className="text-primary text-sm font-normal">Visualization: </span>
        {getTitle()}
      </div>
      <div className="text-sm text-muted-foreground">
        {getSummary()}
      </div>
    </div>
  );
};

export default VisualizationMessage;


