'use client';

import React, { useState, useEffect } from 'react';
import { PanelLeftClose, PanelLeftOpen, Plus, Search, MessageSquare, Settings, MoreVertical, Trash2, Edit, ChevronDown, LogOut, History } from 'lucide-react';
import { ConversationService } from '@/services/api/conversation.service';
import { ConversationSummary } from '@/types';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import DeleteThreadDialog from './DeleteThreadDialog';
import SettingsDialog from './SettingsDialog';
import DarkModeToggle from './DarkModeToggle';
import { useAuth } from '@/lib/contexts/AuthContext';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';

// Hook to detect mobile viewport
const useIsMobile = () => {
  // Initialize with false to prevent hydration mismatch
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };

    // Check on mount to set initial value after hydration
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  return isMobile;
};

interface SidebarProps {
  selectedThreadId?: string;
  onThreadSelect?: (threadId: string | null) => void;
  onNewThread?: () => void;
  onExpandedChange?: (isExpanded: boolean) => void;
  onExecutionHistoryClick?: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  selectedThreadId,
  onThreadSelect,
  onNewThread,
  onExpandedChange,
  onExecutionHistoryClick
}) => {
  const isMobile = useIsMobile();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [threads, setThreads] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [deleteDialog, setDeleteDialog] = useState<{ isOpen: boolean; threadId: string; threadTitle: string }>({
    isOpen: false,
    threadId: '',
    threadTitle: ''
  });
  const { user, signOut } = useAuth();

  // Load threads on mount and when expanded
  useEffect(() => {
    if (threads.length === 0) {
      loadThreads();
    }
  }, []);

  const loadThreads = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await ConversationService.listConversations(50, 0);
      setThreads(response.data?.conversations || []);
    } catch (err: any) {
      // Handle ApiError format
      const errorMessage = err?.message || err?.status || 'Failed to load threads';
      setError(errorMessage);
      console.error('Error loading threads:', {
        error: err,
        message: errorMessage,
        fullError: JSON.stringify(err, null, 2)
      });
    } finally {
      setLoading(false);
    }
  };

  const toggleExpanded = () => {
    const newState = !isExpanded;
    setIsExpanded(newState);
    onExpandedChange?.(newState);
  };

  const handleSettingsClick = () => {
    if (!isExpanded) {
      // If sidebar is collapsed, expand it and open settings
      setIsExpanded(true);
      setIsSettingsOpen(true);
      onExpandedChange?.(true);
    } else {
      // If sidebar is expanded, just toggle settings
      setIsSettingsOpen(!isSettingsOpen);
    }
  };

  const handleThreadSelect = (threadId: string) => {
    onThreadSelect?.(threadId);
    // Close sidebar on mobile when thread is selected
    if (isMobile) {
      setIsExpanded(false);
      onExpandedChange?.(false);
    }
  };

  const handleNewThread = () => {
    onNewThread?.();
    // Close sidebar on mobile when new thread is created
    if (isMobile) {
      setIsExpanded(false);
      onExpandedChange?.(false);
    }
  };

  const handleDeleteThread = (threadId: string, threadTitle: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setDeleteDialog({
      isOpen: true,
      threadId,
      threadTitle: threadTitle || 'Untitled Chat'
    });
  };

  const handleConfirmDelete = async () => {
    try {
      await ConversationService.deleteConversation(deleteDialog.threadId);
      setThreads(prev => prev.filter(t => t.thread_id !== deleteDialog.threadId));

      if (selectedThreadId === deleteDialog.threadId) {
        onThreadSelect?.(null);
      }

      setDeleteDialog({ isOpen: false, threadId: '', threadTitle: '' });
    } catch (err) {
      console.error('Error deleting thread:', err);
      alert('Failed to delete thread');
    }
  };

  const handleCancelDelete = () => {
    setDeleteDialog({ isOpen: false, threadId: '', threadTitle: '' });
  };

  const handleEditTitle = (threadId: string, currentTitle: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setEditingTitle(threadId);
    setNewTitle(currentTitle || 'Untitled Chat');
  };

  const handleSaveTitle = async (threadId: string) => {
    if (!newTitle.trim()) return;

    try {
      await ConversationService.updateTitle(threadId, newTitle.trim());
      setThreads(prev => prev.map(t =>
        t.thread_id === threadId
          ? { ...t, title: newTitle.trim() }
          : t
      ));
      setEditingTitle(null);
      setNewTitle('');
    } catch (err) {
      console.error('Error updating title:', err);
      alert('Failed to update title');
    }
  };

  const handleCancelEdit = () => {
    setEditingTitle(null);
    setNewTitle('');
  };

  const getDateGroup = (dateStr: string): string => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'today';
    if (diffDays === 1) return 'yesterday';
    return 'older';
  };

  const groupThreadsByDate = (threads: ConversationSummary[]) => {
    const grouped: { [key: string]: ConversationSummary[] } = {
      today: [],
      yesterday: [],
      older: []
    };

    threads.forEach(thread => {
      const group = getDateGroup(thread.updated_at);
      grouped[group].push(thread);
    });

    return grouped;
  };

  const filteredThreads = threads.filter(thread =>
    thread.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    thread.last_message_preview?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const groupedThreads = groupThreadsByDate(filteredThreads);

  // Determine sidebar width and behavior based on mobile/desktop
  const getSidebarClasses = () => {
    if (isMobile) {
      // Mobile: overlay-style when expanded
      if (isExpanded) {
        return 'w-96 opacity-100';
      } else {
        return 'w-0 opacity-0';
      }
    } else {
      // Desktop: fixed sidebar with width transition
      return isExpanded ? 'w-82' : 'w-14';
    }
  };

  return (
    <>
      {/* Mobile: Button to open sidebar when collapsed */}
      {isMobile && !isExpanded && (
        <Button
          variant="ghost"
          size="icon"
          onClick={(e) => {
            e.stopPropagation();
            toggleExpanded();
          }}
          className="fixed top-4 left-4 z-50 w-10 h-10 focus:outline-none focus-visible:ring-0 bg-card hover:bg-accent border border-border shadow-sm"
          title="Open sidebar"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </Button>
      )}

      {/* Mobile: Overlay when expanded */}
      {isMobile && isExpanded && (
        <div
          className="fixed inset-0 bg-black/20 z-40"
          onClick={toggleExpanded}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-0 h-[100dvh] bg-background border-r border-sidebar-border transition-all duration-300 ease-in-out z-50 ${getSidebarClasses()} flex flex-col overflow-hidden`}
      >
        <div className={`flex flex-col h-full ${isMobile && isExpanded ? 'w-96 max-w-96' : isMobile ? 'w-0' : 'w-full'} overflow-hidden`}>
          {/* Header */}
          <div className="p-2 space-y-1 border-b border-border overflow-hidden">
            {/* Toggle Button */}
            <button
              onClick={toggleExpanded}
              className="w-full h-10 flex items-center pl-3 bg-transparent hover:bg-accent rounded-md transition-colors"
              title={!isExpanded ? "Expand sidebar" : "Collapse sidebar"}
            >
              {isExpanded ? (
                <PanelLeftClose className="h-5 w-5 flex-shrink-0" />
              ) : (
                <PanelLeftOpen className="h-5 w-5 flex-shrink-0" />
              )}
              {isExpanded && (
                <span className="ml-3 font-semibold whitespace-nowrap overflow-hidden">
                  Explainable Agent
                </span>
              )}
            </button>

            {/* New Thread Button */}
            <button
              onClick={handleNewThread}
              className="w-full h-10 flex items-center pl-3 bg-transparent hover:bg-accent rounded-md transition-colors"
              title={!isExpanded ? "New Thread" : undefined}
            >
              <Plus className="h-5 w-5 flex-shrink-0" />
              {isExpanded && (
                <span className="ml-3 font-medium whitespace-nowrap overflow-hidden">
                  New Thread
                </span>
              )}
            </button>

            {/* Execution History Button */}
            <button
              onClick={onExecutionHistoryClick}
              className="w-full h-10 flex items-center pl-3 bg-transparent hover:bg-accent rounded-md transition-colors"
              title={!isExpanded ? "Execution History" : undefined}
            >
              <History className="h-5 w-5 flex-shrink-0" />
              {isExpanded && (
                <span className="ml-3 font-medium whitespace-nowrap overflow-hidden">
                  Execution History
                </span>
              )}
            </button>
          </div>

          {/* Search Bar - only show when expanded */}
          {isExpanded && (
            <div className="p-3 border-b border-border">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Search chats..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9"
                />
              </div>
            </div>
          )}

          {/* Threads List */}
          <div className="flex-1 overflow-hidden min-w-0">
            <ScrollArea className="h-full w-full">
              {isExpanded ? (
                loading ? (
                  <div className="p-4 text-center text-muted-foreground text-sm">
                    Loading threads...
                  </div>
                ) : error ? (
                  <div className="p-4 text-center text-destructive text-sm">
                    {error}
                    <Button
                      onClick={loadThreads}
                      variant="link"
                      className="block mx-auto mt-2"
                    >
                      Retry
                    </Button>
                  </div>
                ) : filteredThreads.length === 0 ? (
                  <div className="p-4 text-center text-muted-foreground text-sm">
                    {searchQuery ? 'No matching threads' : 'No chat threads found'}
                  </div>
                ) : (
                  <div className="space-y-1 py-2 px-2 min-w-0 max-w-80">
                    {/* Today Section */}
                    {groupedThreads.today.length > 0 && (
                      <>
                        <div className="px-3 py-2">
                          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Today</div>
                        </div>
                        {groupedThreads.today.map((thread) => (
                          <div
                            key={thread.thread_id}
                            className={`relative group rounded-lg transition-colors min-w-0 ${selectedThreadId === thread.thread_id
                              ? 'bg-accent'
                              : 'hover:bg-accent'
                              }`}
                          >
                            <div
                              onClick={() => handleThreadSelect(thread.thread_id)}
                              className="flex items-start gap-2 p-3 cursor-pointer min-w-0 relative"
                            >
                              <div className="min-w-0 flex-1 overflow-hidden group-hover:pr-10">
                                {editingTitle === thread.thread_id ? (
                                  <div className="flex items-center gap-2 min-w-0" onClick={(e) => e.stopPropagation()}>
                                    <Input
                                      type="text"
                                      value={newTitle}
                                      onChange={(e) => setNewTitle(e.target.value)}
                                      onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                          handleSaveTitle(thread.thread_id);
                                        } else if (e.key === 'Escape') {
                                          handleCancelEdit();
                                        }
                                      }}
                                      onBlur={() => handleSaveTitle(thread.thread_id)}
                                      className="flex-1 h-7 text-sm bg-input border-border text-foreground min-w-0 max-w-full"
                                      autoFocus
                                    />
                                  </div>
                                ) : (
                                  <>
                                    <div className="font-medium text-sm text-foreground min-w-0 flex items-center">
                                      <MessageSquare className="w-3 h-3 mr-2 flex-shrink-0" />
                                      <span className="flex-1 truncate min-w-0">{thread.title || 'Untitled Chat'}</span>
                                    </div>
                                    {thread.last_message_preview && (
                                      <div className="text-xs text-muted-foreground truncate whitespace-nowrap mt-0.5 min-w-0 flex-1">
                                        {thread.last_message_preview}
                                      </div>
                                    )}
                                  </>
                                )}
                              </div>

                              {/* Actions Button using shadcn DropdownMenu - only show on hover */}
                              {editingTitle !== thread.thread_id && (
                                <div className="absolute right-3 top-2.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity z-10" onClick={(e) => e.stopPropagation()}>
                                  <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                      <button
                                        className="hover:bg-accent rounded transition-all flex-shrink-0 w-8 h-8 flex items-center justify-center"
                                        title="Thread options"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <MoreVertical className="w-5 h-5 text-foreground" />
                                      </button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="w-36">
                                      <DropdownMenuItem
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleEditTitle(thread.thread_id, thread.title || '', e);
                                        }}
                                        className="cursor-pointer"
                                      >
                                        <Edit className="w-4 h-4 mr-2" />
                                        Rename
                                      </DropdownMenuItem>
                                      <DropdownMenuItem
                                        variant="destructive"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleDeleteThread(thread.thread_id, thread.title || '', e);
                                        }}
                                        className="cursor-pointer"
                                      >
                                        <Trash2 className="w-4 h-4 mr-2" />
                                        Delete
                                      </DropdownMenuItem>
                                    </DropdownMenuContent>
                                  </DropdownMenu>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </>
                    )}

                    {/* Yesterday Section */}
                    {groupedThreads.yesterday.length > 0 && (
                      <>
                        <div className="px-3 py-2">
                          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Yesterday</div>
                        </div>
                        {groupedThreads.yesterday.map((thread) => (
                          <div
                            key={thread.thread_id}
                            className={`relative group rounded-lg transition-colors min-w-0 ${selectedThreadId === thread.thread_id
                              ? 'bg-accent'
                              : 'hover:bg-accent'
                              }`}
                          >
                            <div
                              onClick={() => handleThreadSelect(thread.thread_id)}
                              className="flex items-start gap-2 p-3 cursor-pointer min-w-0 relative"
                            >
                              <div className="min-w-0 flex-1 overflow-hidden group-hover:pr-10">
                                {editingTitle === thread.thread_id ? (
                                  <div className="flex items-center gap-2 min-w-0" onClick={(e) => e.stopPropagation()}>
                                    <Input
                                      type="text"
                                      value={newTitle}
                                      onChange={(e) => setNewTitle(e.target.value)}
                                      onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                          handleSaveTitle(thread.thread_id);
                                        } else if (e.key === 'Escape') {
                                          handleCancelEdit();
                                        }
                                      }}
                                      onBlur={() => handleSaveTitle(thread.thread_id)}
                                      className="flex-1 h-7 text-sm bg-input border-border text-foreground min-w-0 max-w-full"
                                      autoFocus
                                    />
                                  </div>
                                ) : (
                                  <>
                                    <div className="font-medium text-sm text-foreground min-w-0 flex items-center">
                                      <MessageSquare className="w-3 h-3 mr-2 flex-shrink-0" />
                                      <span className="flex-1 truncate min-w-0">{thread.title || 'Untitled Chat'}</span>
                                    </div>
                                    {thread.last_message_preview && (
                                      <div className="text-xs text-muted-foreground truncate whitespace-nowrap mt-0.5 min-w-0 flex-1">
                                        {thread.last_message_preview}
                                      </div>
                                    )}
                                  </>
                                )}
                              </div>

                              {/* Actions Button using shadcn DropdownMenu - only show on hover */}
                              {editingTitle !== thread.thread_id && (
                                <div className="absolute right-3 top-2.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity z-10" onClick={(e) => e.stopPropagation()}>
                                  <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                      <button
                                        className="hover:bg-accent rounded transition-all flex-shrink-0 w-8 h-8 flex items-center justify-center"
                                        title="Thread options"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <MoreVertical className="w-5 h-5 text-foreground" />
                                      </button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="w-36">
                                      <DropdownMenuItem
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleEditTitle(thread.thread_id, thread.title || '', e);
                                        }}
                                        className="cursor-pointer"
                                      >
                                        <Edit className="w-4 h-4 mr-2" />
                                        Rename
                                      </DropdownMenuItem>
                                      <DropdownMenuItem
                                        variant="destructive"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleDeleteThread(thread.thread_id, thread.title || '', e);
                                        }}
                                        className="cursor-pointer"
                                      >
                                        <Trash2 className="w-4 h-4 mr-2" />
                                        Delete
                                      </DropdownMenuItem>
                                    </DropdownMenuContent>
                                  </DropdownMenu>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </>
                    )}

                    {/* Older Section */}
                    {groupedThreads.older.length > 0 && (
                      <>
                        <div className="px-3 py-2">
                          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Older</div>
                        </div>
                        {groupedThreads.older.map((thread) => (
                          <div
                            key={thread.thread_id}
                            className={`relative group rounded-lg transition-colors min-w-0 ${selectedThreadId === thread.thread_id
                              ? 'bg-accent'
                              : 'hover:bg-accent'
                              }`}
                          >
                            <div
                              onClick={() => handleThreadSelect(thread.thread_id)}
                              className="flex items-start gap-2 p-3 cursor-pointer min-w-0 relative"
                            >
                              <div className="min-w-0 flex-1 overflow-hidden group-hover:pr-10">
                                {editingTitle === thread.thread_id ? (
                                  <div className="flex items-center gap-2 min-w-0" onClick={(e) => e.stopPropagation()}>
                                    <Input
                                      type="text"
                                      value={newTitle}
                                      onChange={(e) => setNewTitle(e.target.value)}
                                      onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                          handleSaveTitle(thread.thread_id);
                                        } else if (e.key === 'Escape') {
                                          handleCancelEdit();
                                        }
                                      }}
                                      onBlur={() => handleSaveTitle(thread.thread_id)}
                                      className="flex-1 h-7 text-sm bg-input border-border text-foreground min-w-0 max-w-full"
                                      autoFocus
                                    />
                                  </div>
                                ) : (
                                  <>
                                    <div className="font-medium text-sm text-foreground min-w-0 flex items-center">
                                      <MessageSquare className="w-3 h-3 mr-2 flex-shrink-0" />
                                      <span className="flex-1 truncate min-w-0">{thread.title || 'Untitled Chat'}</span>
                                    </div>
                                    {thread.last_message_preview && (
                                      <div className="text-xs text-muted-foreground truncate whitespace-nowrap mt-0.5 min-w-0 flex-1">
                                        {thread.last_message_preview}
                                      </div>
                                    )}
                                  </>
                                )}
                              </div>

                              {/* Actions Button using shadcn DropdownMenu - only show on hover */}
                              {editingTitle !== thread.thread_id && (
                                <div className="absolute right-3 top-2.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity z-10" onClick={(e) => e.stopPropagation()}>
                                  <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                      <button
                                        className="hover:bg-accent rounded transition-all flex-shrink-0 w-8 h-8 flex items-center justify-center"
                                        title="Thread options"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        <MoreVertical className="w-5 h-5 text-foreground" />
                                      </button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="w-36">
                                      <DropdownMenuItem
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleEditTitle(thread.thread_id, thread.title || '', e);
                                        }}
                                        className="cursor-pointer"
                                      >
                                        <Edit className="w-4 h-4 mr-2" />
                                        Rename
                                      </DropdownMenuItem>
                                      <DropdownMenuItem
                                        variant="destructive"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleDeleteThread(thread.thread_id, thread.title || '', e);
                                        }}
                                        className="cursor-pointer"
                                      >
                                        <Trash2 className="w-4 h-4 mr-2" />
                                        Delete
                                      </DropdownMenuItem>
                                    </DropdownMenuContent>
                                  </DropdownMenu>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                )
              ) : null}
            </ScrollArea>
          </div>

          {/* Footer */}
          <div className="p-2 mb-2 border-t border-border overflow-hidden space-y-1 pb-[env(safe-area-inset-bottom)]">
            {isExpanded && (
              <Button
                onClick={loadThreads}
                variant="ghost"
                className="w-full h-10 text-xs text-muted-foreground hover:text-foreground hover:bg-accent justify-start pl-3"
              >
                Refresh Threads
              </Button>
            )}

            {/* Settings Button */}
            {isExpanded ? (
              <>
                <button
                  onClick={() => setIsSettingsOpen(true)}
                  className="w-full h-10 flex items-center pl-3 bg-transparent hover:bg-accent rounded-md transition-colors"
                  title="Settings"
                >
                  <Settings className="w-4 h-4 flex-shrink-0" />
                  <span className="ml-2 text-xs font-medium whitespace-nowrap overflow-hidden">
                    Settings
                  </span>
                </button>

                {/* Logout Button */}
                <button
                  onClick={async () => { await signOut(); }}
                  className="w-full h-10 flex items-center gap-2 px-3 text-xs text-muted-foreground hover:text-foreground bg-transparent hover:bg-accent rounded-md min-w-0"
                >
                  <LogOut className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate min-w-0 flex-1">
                    Sign out{user?.email ? ` (${user.email})` : ''}
                  </span>
                </button>
              </>
            ) : (
              <button
                onClick={() => {
                  setIsExpanded(true);
                  setIsSettingsOpen(true);
                  onExpandedChange?.(true);
                }}
                className="w-full h-10 flex items-center pl-3 bg-transparent hover:bg-accent rounded-md transition-colors"
                title="Settings"
              >
                <Settings className="w-4 h-4 flex-shrink-0" />
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* Settings Dialog */}
      <SettingsDialog
        open={isSettingsOpen}
        onOpenChange={setIsSettingsOpen}
      />

      {/* Delete Thread Dialog */}
      <DeleteThreadDialog
        isOpen={deleteDialog.isOpen}
        threadTitle={deleteDialog.threadTitle}
        onClose={handleCancelDelete}
        onConfirm={handleConfirmDelete}
      />
    </>
  );
};

export default Sidebar;