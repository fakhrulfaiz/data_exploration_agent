import React from 'react';

const LoadingIndicator: React.FC = () => {
    return (
        <div className="w-full h-[60vh] flex items-center justify-center bg-transparent">
            <div className="flex items-center gap-3 text-blue-600 dark:text-blue-400">
                <span className="sr-only">Loading</span>
                <div className="w-3 h-3 rounded-full bg-current animate-bounce [animation-delay:-0.3s]"></div>
                <div className="w-3 h-3 rounded-full bg-current animate-bounce [animation-delay:-0.15s]"></div>
                <div className="w-3 h-3 rounded-full bg-current animate-bounce"></div>
            </div>
        </div>
    );
};

export default LoadingIndicator;
