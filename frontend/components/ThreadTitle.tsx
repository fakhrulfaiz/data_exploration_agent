'use client'

import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, ChevronUp, Edit3, Check, X } from 'lucide-react';
import { ConversationService } from '@/services/api/conversation.service';

interface ThreadTitleProps {
  title: string;
  threadId?: string;
  onTitleChange?: (newTitle: string) => void;
  className?: string;
}

const ThreadTitle: React.FC<ThreadTitleProps> = ({
  title,
  threadId,
  onTitleChange,
  className = ""
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(title);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setIsEditing(false);
        setEditValue(title);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [title]);

  // Focus input when editing starts
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  // Update edit value when title prop changes
  useEffect(() => {
    setEditValue(title);
  }, [title]);

  const handleToggleDropdown = () => {
    setIsOpen(!isOpen);
  };

  const handleStartEdit = () => {
    setIsEditing(true);
    setEditValue(title);
  };

  const handleSaveEdit = async () => {
    if (!editValue.trim() || editValue === title) return;

    try {
      // If we have a threadId, update via API like in Sidebar
      if (threadId) {
        await ConversationService.updateTitle(threadId, editValue.trim());
      }

      // Always call the parent callback to update local state
      if (onTitleChange) {
        onTitleChange(editValue.trim());
      }

      setIsEditing(false);
      setIsOpen(false);
    } catch (err) {
      console.error('Error updating title:', err);
      alert('Failed to update title');
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditValue(title);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveEdit();
    } else if (e.key === 'Escape') {
      handleCancelEdit();
    }
  };

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Thread Title Button */}
      <button
        onClick={handleToggleDropdown}
        className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-foreground bg-transparent hover:bg-accent rounded-lg transition-colors max-w-xs"
      >
        <span className="truncate flex-1 text-left">
          {title || 'New Thread'}
        </span>
        {isOpen ? (
          <ChevronUp className="w-4 h-4 flex-shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 flex-shrink-0" />
        )}
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-card border border-border rounded-lg shadow-lg z-50">
          <div className="p-3">
            {isEditing ? (
              /* Edit Mode */
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">
                    Thread Title
                  </label>
                  <input
                    ref={inputRef}
                    type="text"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    className="w-full px-3 py-2 text-sm border border-border rounded-md focus:outline-none focus:ring-2 focus:ring-primary bg-input text-foreground"
                    placeholder="Enter thread title..."
                  />
                </div>
                <div className="flex items-center gap-2 justify-end">
                  <button
                    onClick={handleCancelEdit}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground hover:text-foreground bg-transparent transition-colors"
                  >
                    <X className="w-3 h-3" />
                    Cancel
                  </button>
                  <button
                    onClick={handleSaveEdit}
                    disabled={!editValue.trim() || editValue === title}
                    className="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-primary-foreground rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <Check className="w-3 h-3" />
                    Save
                  </button>
                </div>
              </div>
            ) : (
              /* View Mode */
              <div className="space-y-2">
                <div className="text-sm text-foreground font-medium">
                  {title || 'New Thread'}
                </div>
                <button
                  onClick={handleStartEdit}
                  className="flex items-center gap-2 w-full px-2 py-1.5 text-xs text-muted-foreground hover:text-foreground bg-transparent hover:bg-accent rounded transition-colors"
                >
                  <Edit3 className="w-3 h-3" />
                  Edit title
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ThreadTitle;
