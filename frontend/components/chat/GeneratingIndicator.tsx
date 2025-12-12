import React from 'react';

interface GeneratingIndicatorProps {
  activeTools?: string[];
}

const GeneratingIndicator: React.FC<GeneratingIndicatorProps> = ({ activeTools }) => {
  return (
    <div className="flex justify-start">
      <div className="bg-muted px-4 py-3 rounded-lg">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce"></div>
          <div 
            className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" 
            style={{ animationDelay: '0.1s' }}
          ></div>
          <div 
            className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" 
            style={{ animationDelay: '0.2s' }}
          ></div>
          <span className="text-muted-foreground text-sm ml-2">Generating...</span>
        </div>
        {activeTools && activeTools.length > 0 && (
          <div className="mt-2 space-y-1">
            {activeTools.map((tool, i) => (
              <div key={i} className="text-xs text-primary flex items-center gap-1">
                <div className="w-2 h-2 bg-primary rounded-full animate-pulse" />
                Using {tool}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default GeneratingIndicator;