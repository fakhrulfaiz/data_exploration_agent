'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import LoadingIndicator from '@/components/LoadingIndicator';

interface LoadingContextType {
    isLoading: boolean;
    setLoading: (loading: boolean) => void;
}

const LoadingContext = createContext<LoadingContextType | undefined>(undefined);

export const useLoading = () => {
    const context = useContext(LoadingContext);
    if (context === undefined) {
        throw new Error('useLoading must be used within a LoadingProvider');
    }
    return context;
};

interface LoadingProviderProps {
    children: React.ReactNode;
}

export const LoadingProvider: React.FC<LoadingProviderProps> = ({ children }) => {
    const [isLoading, setIsLoading] = useState(false);
    const pathname = usePathname();
    const searchParams = useSearchParams();

    // Auto-detect route changes
    useEffect(() => {
        setIsLoading(false);
    }, [pathname, searchParams]);

    const setLoading = (loading: boolean) => {
        setIsLoading(loading);
    };

    const value: LoadingContextType = {
        isLoading,
        setLoading,
    };

    return (
        <LoadingContext.Provider value={value}>
            {isLoading && (
                <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm">
                    <LoadingIndicator />
                </div>
            )}
            {children}
        </LoadingContext.Provider>
    );
};
