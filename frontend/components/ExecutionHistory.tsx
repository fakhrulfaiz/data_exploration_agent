'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { History, ArrowLeft, Clock, Hash, MessageSquare, Loader2, Search, MessageCircle } from 'lucide-react';
import { ConversationService } from '@/services';
import type { CheckpointSummary } from '@/types';
import { Card, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { ScrollArea } from './ui/scroll-area';
import { Input } from './ui/input';

interface ExecutionHistoryProps {
  onCheckpointClick: (checkpointId: string, threadId: string) => void;
  onBack?: () => void;
}

const ExecutionHistory: React.FC<ExecutionHistoryProps> = ({ onCheckpointClick, onBack }) => {
  const [checkpoints, setCheckpoints] = useState<CheckpointSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');

  useEffect(() => {
    loadCheckpoints();
  }, []);

  const loadCheckpoints = async () => {
    try {
      setLoading(true);
      setError(null);
      // Limit to 20 checkpoints for better performance and UI
      const response = await ConversationService.listCheckpoints(20, 0);
      setCheckpoints(response.data?.checkpoints || []);
    } catch (err: any) {
      // Handle different error types
      let errorMessage = 'Failed to load execution history';

      if (err?.message) {
        errorMessage = err.message;
      } else if (err?.status === 'error' && err?.errors?.length > 0) {
        errorMessage = err.errors[0].message;
      } else if (typeof err === 'string') {
        errorMessage = err;
      }

      setError(errorMessage);
      console.error('Error loading checkpoints:', {
        message: errorMessage,
        fullError: err,
        status: err?.status,
        errors: err?.errors
      });
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };


  const handleCheckpointClick = async (checkpoint: CheckpointSummary) => {
    // Call the parent handler which will fetch explorer data and open ExplorerPanel
    onCheckpointClick(checkpoint.checkpoint_id, checkpoint.thread_id);
  };

  // Filter checkpoints based on search query
  const filteredCheckpoints = useMemo(() => {
    if (!searchQuery.trim()) {
      return checkpoints;
    }
    const query = searchQuery.toLowerCase();
    return checkpoints.filter(checkpoint =>
      checkpoint.checkpoint_id.toLowerCase().includes(query) ||
      checkpoint.thread_id.toLowerCase().includes(query) ||
      checkpoint.message_type?.toLowerCase().includes(query) ||
      checkpoint.query?.toLowerCase().includes(query)
    );
  }, [checkpoints, searchQuery]);

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border">
        <div className="flex items-center gap-3">
          {onBack && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onBack}
              className="hover:bg-accent"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
          )}
          <div className="flex items-center gap-2">
            <History className="h-5 w-5" />
            <h2 className="text-xl font-semibold">Execution History</h2>
          </div>
        </div>
      </div>

      {/* Search Bar */}
      <div className="p-4 border-b border-border">
        <div className="max-w-3xl mx-auto">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search by checkpoint ID, thread ID, or type..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9"
            />
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="flex flex-col items-center gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              <p className="text-muted-foreground">Loading execution history...</p>
            </div>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
            <p className="text-destructive">{error}</p>
            <Button onClick={loadCheckpoints} variant="outline">
              Retry
            </Button>
          </div>
        ) : filteredCheckpoints.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-4 p-8">
            <History className="h-12 w-12 text-muted-foreground" />
            <p className="text-muted-foreground text-center">
              {searchQuery ? 'No checkpoints match your search.' : 'No execution history found. Checkpoints will appear here after running agent executions.'}
            </p>
          </div>
        ) : (
          <ScrollArea className="h-full">
            <div className="max-w-3xl mx-auto px-4 py-3 space-y-2">
              {filteredCheckpoints.map((checkpoint) => (
                <Card
                  key={checkpoint.checkpoint_id}
                  className="cursor-pointer hover:bg-accent/50 transition-colors py-4"
                  onClick={() => handleCheckpointClick(checkpoint)}
                >
                  <CardHeader className="px-4">
                    <div className="flex flex-col gap-1">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <CardTitle className="text-xs flex items-center gap-1.5 mb-0.5">
                            <span className="font-mono text-xs break-all px-2 py-0.5 rounded bg-secondary text-secondary-foreground">
                              {checkpoint.checkpoint_id}
                            </span>
                          </CardTitle>
                          {checkpoint.query && (
                            <div className="flex items-start gap-1.5 mt-0.5">
                              <span className="text-md text-foreground break-words font-medium">
                                {checkpoint.query}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                      <CardDescription className="flex flex-col gap-0.5 text-xs mt-0.5">
                        <span className="flex items-center gap-1.5">
                          <Clock className="h-3 w-3 flex-shrink-0" />
                          <span className="text-xs">{formatDate(checkpoint.timestamp)}</span>
                        </span>
                        <span className="flex items-center gap-1.5">
                          <MessageSquare className="h-3 w-3 flex-shrink-0" />
                          <span className="font-mono text-xs break-all">
                            {checkpoint.thread_id}
                          </span>
                        </span>
                      </CardDescription>
                    </div>
                  </CardHeader>
                </Card>
              ))}
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  );
};

export default ExecutionHistory;

