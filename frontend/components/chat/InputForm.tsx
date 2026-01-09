'use client'

import React, { useState, useRef } from 'react';
import { ArrowUp, Upload, X, Check, Brain, Zap, Layers, File, Image, FileText, FileCode, Plus, Loader2, Trash2, Database, Network } from 'lucide-react';
import {
  InputGroup,
  InputGroupTextarea,
  InputGroupAddon,
  InputGroupButton,
  InputGroupText,
} from '@/components/ui/input-group';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { Separator } from '@/components/ui/separator';
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from '@/components/ui/carousel';
// import LLMSelector from './LLMSelector';
import { uploadAttachments, deleteAttachment } from '@/services/api/storage.service';
import { UploadedAttachment } from '@/types/attachments';

interface InputFormProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  placeholder?: string;
  disabled?: boolean;
  isLoading?: boolean;
  usePlanning?: boolean;
  useExplainer?: boolean;
  useStreaming?: boolean;
  onPlanningToggle?: (enabled: boolean) => void;
  onExplainerToggle?: (enabled: boolean) => void;
  onStreamingToggle?: (enabled: boolean) => void;
  onFilesChange?: (files: File[]) => void;
  attachedFiles?: File[];
  onAttachmentsUploaded?: (files: UploadedAttachment[]) => void;
  onAttachmentUploadError?: (message: string) => void;
  onAttachmentDeleted?: (attachment: UploadedAttachment) => void;
  hasDataContext?: boolean;
  onOpenDataContext?: () => void;
  isStreaming?: boolean;
  onStopStream?: () => void;
  onToggleGraphPanel?: () => void; // Callback to toggle graph panel
}

const InputForm: React.FC<InputFormProps> = ({
  value,
  onChange,
  onSend,
  onKeyDown,
  placeholder = "Ask, Search or Chat...",
  disabled = false,
  isLoading = false,
  usePlanning = false,
  useExplainer = false,
  useStreaming: useStreamingProp,
  onPlanningToggle,
  onExplainerToggle,
  onStreamingToggle,
  onFilesChange,
  attachedFiles = [],
  onAttachmentsUploaded,
  onAttachmentUploadError,
  onAttachmentDeleted,
  hasDataContext,
  onOpenDataContext,
  isStreaming = false,
  onStopStream,
  onToggleGraphPanel,
}) => {
  const useStreaming = useStreamingProp ?? true;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isTextareaExpanded, setIsTextareaExpanded] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [uploadedFileMap, setUploadedFileMap] = useState<Record<string, UploadedAttachment>>({});

  const getFileKey = (file: File) => `${file.name}-${file.size}-${file.lastModified}`;

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const files = Array.from(e.target.files || []);
    if (onFilesChange) {
      onFilesChange([...attachedFiles, ...files]);
    }
  };

  const removeFile = async (index: number): Promise<void> => {
    const target = attachedFiles[index];
    if (!target) return;
    const key = getFileKey(target);
    const uploadedAttachment = uploadedFileMap[key];

    if (uploadedAttachment) {
      setUploadStatus('Deleting attachment...');
      try {
        await deleteAttachment(uploadedAttachment.path);
        setUploadedFileMap((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
        onAttachmentDeleted?.(uploadedAttachment);
        setUploadStatus('Attachment deleted');
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Delete failed';
        setUploadStatus(message);
        onAttachmentUploadError?.(message);
      }
    }

    if (onFilesChange) {
      onFilesChange(attachedFiles.filter((_, i) => i !== index));
    }
  };

  const handleTextareaInput = (e: React.FormEvent<HTMLTextAreaElement>) => {
    const target = e.target as HTMLTextAreaElement;
    target.style.height = 'auto';
    target.style.height = `${target.scrollHeight}px`;

    // Check if content exceeds max height (max-h-64 = 16rem = 256px)
    const maxHeight = 256; // 16rem in pixels
    setIsTextareaExpanded(target.scrollHeight > maxHeight);
  };

  const handleUploadAttachments = async () => {
    if (!attachedFiles.length || isUploading) {
      return;
    }

    const filesToUpload = attachedFiles.filter(
      (file) => !uploadedFileMap[getFileKey(file)]
    );

    if (!filesToUpload.length) {
      setUploadStatus('All files already uploaded');
      return;
    }

    setIsUploading(true);
    setUploadStatus(null);
    try {
      const uploaded = await uploadAttachments(filesToUpload);
      const mapUpdates: Record<string, UploadedAttachment> = {};
      filesToUpload.forEach((file, idx) => {
        mapUpdates[getFileKey(file)] = uploaded[idx];
      });
      setUploadedFileMap((prev) => ({ ...prev, ...mapUpdates }));
      setUploadStatus(
        `${uploaded.length} file${uploaded.length > 1 ? 's' : ''} uploaded`
      );
      onAttachmentsUploaded?.(uploaded);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Upload failed';
      setUploadStatus(message);
      onAttachmentUploadError?.(message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleTextareaKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    } else {
      onKeyDown(e);
    }
  };

  // Check expansion state when value changes
  React.useEffect(() => {
    if (textareaRef.current) {
      const maxHeight = 256; // 16rem in pixels
      setIsTextareaExpanded(textareaRef.current.scrollHeight > maxHeight);
    }
  }, [value]);

  React.useEffect(() => {
    setUploadedFileMap((prev) => {
      const activeKeys = new Set(attachedFiles.map(getFileKey));
      let hasChanges = false;
      const next: Record<string, UploadedAttachment> = {};
      Object.entries(prev).forEach(([key, value]) => {
        if (activeKeys.has(key)) {
          next[key] = value;
        } else {
          hasChanges = true;
        }
      });
      return hasChanges ? next : prev;
    });
  }, [attachedFiles]);

  const getFileIcon = (file: File) => {
    const fileType = file.type;
    if (fileType.startsWith('image/')) return <Image className="w-3 h-3" />;
    if (fileType.includes('text/') || fileType.includes('document')) return <FileText className="w-3 h-3" />;
    if (fileType.includes('code') || fileType.includes('javascript') || fileType.includes('json')) return <FileCode className="w-3 h-3" />;
    return <File className="w-3 h-3" />;
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const renderAttachmentChip = (file: File, index: number) => {
    const key = getFileKey(file);
    const isUploaded = Boolean(uploadedFileMap[key]);

    return (
      <div
        key={`${file.name}-${index}`}
        className="flex items-center gap-2 px-3 py-1.5 bg-accent text-accent-foreground rounded-full text-xs border border-border"
      >
        <div className="flex items-center gap-1.5">
          {getFileIcon(file)}
          <div className="flex flex-col">
            <span className="truncate max-w-32 font-medium">{file.name}</span>
            <span className="text-[10px] text-muted-foreground">
              {formatFileSize(file.size)}
            </span>
            {isUploaded && (
              <span className="text-[10px] text-emerald-500 font-semibold flex items-center gap-1">
                <Check className="w-3 h-3" />
                Uploaded
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => removeFile(index)}
          className="text-accent-foreground hover:bg-accent p-0.5 rounded-full transition-colors"
        >
          {isUploaded ? <Trash2 className="w-3 h-3" /> : <X className="w-3 h-3" />}
        </button>
      </div>
    );
  }

  const useCarousel = attachedFiles.length > 3;
  const pendingUploadCount = attachedFiles.filter(
    (file) => !uploadedFileMap[getFileKey(file)]
  ).length;

  return (
    <div className="w-full max-w-3xl mx-auto space-y-2">

      {/* Input Group */}
      <InputGroup className="rounded-3xl px-2 bg-muted">
        {/* Attached Files Display */}
        {attachedFiles.length > 0 && (
          <div className="py-2 border-b border-border w-full">
            {useCarousel ? (
              <Carousel
                className="relative w-full group max-w-full"
                opts={{ align: 'start', loop: false }}
              >
                <CarouselContent className="-ml-3 pr-3">
                  {attachedFiles.map((file, index) => (
                    <CarouselItem
                      key={`${file.name}-${index}`}
                      className="basis-[220px] pl-3"
                    >
                      {renderAttachmentChip(file, index)}
                    </CarouselItem>
                  ))}
                </CarouselContent>
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-muted to-transparent transition-opacity duration-200 opacity-100 group-hover:opacity-100"
                />
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-muted to-transparent transition-opacity duration-200 opacity-100 group-hover:opacity-100"
                />
                <CarouselPrevious className="left-2 top-1/2 -translate-y-1/2 size-7 opacity-0 transition duration-200 group-hover:opacity-100 bg-background/60 border border-border/70 hover:bg-background/90" />
                <CarouselNext className="right-2 top-1/2 -translate-y-1/2 size-7 opacity-0 transition duration-200 group-hover:opacity-100 bg-background/60 border border-border/70 hover:bg-background/90" />
              </Carousel>
            ) : (
              <div className="flex flex-wrap gap-2 justify-start">
                {attachedFiles.map((file, index) => renderAttachmentChip(file, index))}
              </div>
            )}
            <div className="flex flex-col gap-1 mt-3 sm:flex-row sm:items-center sm:justify-between">
              <button
                type="button"
                onClick={handleUploadAttachments}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-foreground text-background text-xs font-medium disabled:opacity-60 disabled:cursor-not-allowed"
                disabled={isUploading || pendingUploadCount === 0}
              >
                {isUploading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Upload className="w-3.5 h-3.5" />
                )}
                {isUploading
                  ? 'Uploading...'
                  : pendingUploadCount === 0
                    ? 'All uploaded'
                    : 'Upload to Supabase'}
              </button>
              {uploadStatus && (
                <span className="text-xs text-muted-foreground">{uploadStatus}</span>
              )}
            </div>
          </div>
        )}

        <InputGroupTextarea
          ref={textareaRef}
          className={`rounded-3xl resize-none mt-1 max-h-64 min-h-[5rem] textarea-scroll bg-transparent text-foreground placeholder:text-muted-foreground ${isTextareaExpanded ? 'overflow-y-auto' : 'overflow-y-hidden'
            }`}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleTextareaKeyDown}
          onInput={handleTextareaInput}
          disabled={disabled || isLoading}
          rows={1}
        />
        <InputGroupAddon align="block-end">
          {/* Options Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <InputGroupButton
                variant="outline"
                className="rounded-xl"
                size="icon-sm"
              >
                <Plus className="w-4 h-4" strokeWidth={3} />
              </InputGroupButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              side="top"
              align="start"
              className="[--radius:0.95rem] min-w-40"
              onMouseDown={(e: React.MouseEvent<HTMLDivElement>) => e.preventDefault()}
            >
              <DropdownMenuItem onClick={(e: React.MouseEvent<HTMLDivElement>) => {
                e.preventDefault();
                onPlanningToggle?.(!usePlanning);
              }}>
                <Layers className={`w-4 h-4 mr-2 ${usePlanning ? 'text-blue-600' : ''}`} />
                Planning
                {usePlanning && <Check className="w-4 h-4 ml-auto text-blue-600" />}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={(e: React.MouseEvent<HTMLDivElement>) => {
                e.preventDefault();
                onExplainerToggle?.(!useExplainer);
              }}>
                <Brain className={`w-4 h-4 mr-2 ${useExplainer ? 'text-emerald-600' : ''}`} />
                Explainer
                {useExplainer && <Check className="w-4 h-4 ml-auto text-emerald-600" />}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={(e: React.MouseEvent<HTMLDivElement>) => {
                e.preventDefault();
                onStreamingToggle?.(!useStreaming);
              }}>
                <Zap className={`w-4 h-4 mr-2 ${useStreaming ? 'text-purple-600' : ''}`} />
                Streaming
                {useStreaming && <Check className="w-4 h-4 ml-auto text-purple-600" />}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={(e: React.MouseEvent<HTMLDivElement>) => {
                e.preventDefault();
                fileInputRef.current?.click();
              }}>
                <Upload className="w-4 h-4 mr-2" />
                Upload File
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Data Context button (if available) */}
          {hasDataContext && (
            <InputGroupButton
              type="button"
              variant="outline"
              className="rounded-xl ml-2"
              size="icon-sm"
              onClick={onOpenDataContext}
            >
              <Database className="w-4 h-4 text-primary" />
            </InputGroupButton>
          )}

          {/* Graph Flow Panel Toggle */}
          {onToggleGraphPanel && (
            <InputGroupButton
              type="button"
              variant="outline"
              className="rounded-xl ml-2"
              size="icon-sm"
              onClick={onToggleGraphPanel}
              title="Toggle Agent Flow Visualization"
            >
              <Network className="w-4 h-4 text-purple-600" />
            </InputGroupButton>
          )}

          {/* LLM Selector */}
          {/* <LLMSelector compact /> */}
          <InputGroupText className="text-muted-foreground text-xs">GPT-4</InputGroupText>

          <InputGroupText className="ml-auto text-muted-foreground">52% used</InputGroupText>

          <Separator orientation="vertical" className="!h-4" />

          {/* Send/Stop Button */}
          {isStreaming ? (
            <InputGroupButton
              variant="destructive"
              className="rounded-xl"
              size="icon-sm"
              onClick={onStopStream}
              title="Stop stream"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="1" />
              </svg>
              <span className="sr-only">Stop</span>
            </InputGroupButton>
          ) : (
            <InputGroupButton
              variant="default"
              className="rounded-xl"
              size="icon-sm"
              disabled={!value.trim() || disabled || isLoading}
              onClick={onSend}
            >
              <ArrowUp className="w-5 h-5 text-background" strokeWidth={3} />
              <span className="sr-only">Send</span>
            </InputGroupButton>
          )}
        </InputGroupAddon>
      </InputGroup>

      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*"
        onChange={handleFileUpload}
        className="hidden"
      />
    </div>
  );
};

export default InputForm;