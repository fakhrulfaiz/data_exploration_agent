// Content block types for structured messages
export interface TextContent {
  text: string;
}

export interface ToolCallsContent {
  toolCalls: Array<{
    name: string;
    input: any;
    output?: any;
    status: 'pending' | 'approved' | 'rejected';
  }>;
  content?: string; // Tool explanation text from tool_explanation node
}


export interface ExplorerContent {
  checkpointId: string;
  explorerData?: any; // Optional cached data
}

export interface VisualizationsContent {
  checkpointId: string;
  visualizations?: any[]; // Optional cached data
}

export interface PlanContent {
  plan: string;
}

export interface ContentBlock {
  id: string;
  type: 'text' | 'tool_calls' | 'explorer' | 'visualizations' | 'plan';
  needsApproval?: boolean;
  messageStatus?: 'pending' | 'approved' | 'rejected' | 'error' | 'timeout';
  data: TextContent | ToolCallsContent | ExplorerContent | VisualizationsContent | PlanContent;
}

export interface Message {
  id: number; // Frontend numeric ID for React keys
  message_id?: string; // Backend UUID message identifier
  role: 'user' | 'assistant';
  // Content is always an array of content blocks
  content: ContentBlock[];
  timestamp: Date;
  needsApproval?: boolean;
  messageStatus?: 'pending' | 'approved' | 'rejected' | 'error' | 'timeout';
  isStreaming?: boolean;
  threadId?: string;
  // Deprecated: keeping for backward compatibility during transition
  messageType?: 'message' | 'explorer' | 'visualization' | 'tool_call';
  checkpointId?: string;
  metadata?: {
    explorerData?: any;
    visualizations?: any[];
    toolCalls?: Array<{
      id: string;
      name: string;
      input: any;
      output?: any;
      status: 'pending' | 'approved' | 'rejected';
    }>;
    [key: string]: any;
  };
}

// Helper functions for content blocks
export const createTextBlock = (id: string, text: string, needsApproval?: boolean): ContentBlock => ({
  id,
  type: 'text',
  needsApproval,
  data: { text }
});

export const createToolCallsBlock = (id: string, toolCalls: ToolCallsContent['toolCalls'], needsApproval?: boolean): ContentBlock => ({
  id,
  type: 'tool_calls',
  needsApproval,
  data: { toolCalls }
});


export const createExplorerBlock = (id: string, checkpointId: string, needsApproval?: boolean, explorerData?: any): ContentBlock => ({
  id,
  type: 'explorer',
  needsApproval,
  data: { checkpointId, explorerData }
});

export const createVisualizationsBlock = (id: string, checkpointId: string, needsApproval?: boolean, visualizations?: any[]): ContentBlock => ({
  id,
  type: 'visualizations',
  needsApproval,
  data: { checkpointId, visualizations }
});

// Type guards for content blocks
export const isTextBlock = (block: ContentBlock): block is ContentBlock & { data: TextContent } =>
  block.type === 'text';

export const isToolCallsBlock = (block: ContentBlock): block is ContentBlock & { data: ToolCallsContent } =>
  block.type === 'tool_calls';

export const isExplorerBlock = (block: ContentBlock): block is ContentBlock & { data: ExplorerContent } =>
  block.type === 'explorer';

export const isVisualizationsBlock = (block: ContentBlock): block is ContentBlock & { data: VisualizationsContent } =>
  block.type === 'visualizations';

export const createPlanBlock = (id: string, plan: string, needsApproval?: boolean): ContentBlock => ({
  id,
  type: 'plan',
  needsApproval,
  data: { plan }
});

export const isPlanBlock = (block: ContentBlock): block is ContentBlock & { data: PlanContent } =>
  block.type === 'plan';

// Response object that handlers can return
export interface HandlerResponse {
  message: string;
  needsApproval?: boolean;
  explorerData?: any;
  visualizations?: any[];
  checkpoint_id?: string; // Add checkpoint ID for both explorer and visualization messages
  response_type?: 'answer' | 'replan' | 'cancel';  // Type of response from backend
  backendMessageId?: string; // Backend-generated UUID message ID for assistant messages
  explorerMessageId?: number; // Backend-generated message ID for explorer messages
  visualizationMessageId?: number; // Backend-generated message ID for visualization messages
  // New streaming properties
  isStreaming?: boolean;
  streamingHandler?: (
    streamingMessageId: number,
    updateContentCallback: (id: number, contentBlocks: ContentBlock[]) => void,
    onStatus?: (status: 'user_feedback' | 'finished' | 'running' | 'error' | 'tool_call' | 'tool_result' | 'completed_payload' | 'visualizations_ready' | 'content_block', eventData?: string, responseType?: 'answer' | 'replan' | 'cancel') => void
  ) => Promise<void>;
}


export interface ChatComponentProps {
  onSendMessage: (message: string, messageHistory: Message[], options?: { usePlanning?: boolean; useExplainer?: boolean; attachedFiles?: File[] }) => Promise<HandlerResponse>;
  onApprove?: (content: string, message: Message) => Promise<HandlerResponse | void> | HandlerResponse | void;
  onFeedback?: (content: string, message: Message) => Promise<HandlerResponse | void> | HandlerResponse | void;
  onCancel?: (content: string, message: Message) => Promise<string> | string;
  onRetry?: (message: Message) => Promise<HandlerResponse | void> | HandlerResponse | void;
  currentThreadId?: string | null;
  initialMessages?: Message[];
  className?: string;
  placeholder?: string;
  disabled?: boolean;
  onMessageUpdated?: (message: Message) => void;
  threadTitle?: string;
  onTitleChange?: (newTitle: string) => void;
  sidebarExpanded?: boolean;
  hasDataContext?: boolean;
  onOpenDataContext?: () => void;
}

export interface MessageComponentProps {
  message: Message;
  onRetry?: (messageId: number) => void;
}


// Graph API Types
export interface StartRequest {
  human_request: string;
  thread_id?: string; // Optional thread ID for existing conversations
  use_planning?: boolean; // Whether to use planning in agent execution
  use_explainer?: boolean; // Whether to use explainer node for step explanations
  agent_type?: string; // Type of agent to use
}

export interface ResumeRequest {
  thread_id: string;
  review_action: 'approved' | 'feedback' | 'cancelled';
  human_comment?: string;
}

export interface StepExplanation {
  id: number;
  type: string;
  input: string;
  output: string;
  timestamp: string;
  decision?: string;
  reasoning?: string;
  confidence?: number;
  why_chosen?: string;
}

export interface FinalResult {
  Summary: string;
  details: string;
  source: string;
  inference: string;
  extra_explanation: string;
}

export interface GraphResponse {
  thread_id: string;
  checkpoint_id?: string; // Add checkpoint ID field
  run_status: 'user_feedback' | 'finished' | 'error';
  assistant_response?: string;
  query?: string;  // User's original question
  plan?: string;
  error?: string;
  steps?: StepExplanation[];
  final_result?: FinalResult;
  total_time?: number;
  overall_confidence?: number;
  response_type?: 'answer' | 'replan' | 'cancel';  // Type of response from planner
  visualizations?: any[]; // Visualization specs for frontend rendering
  assistant_message_id?: string; // Backend-generated UUID message ID for assistant messages
}

export interface GraphStatus {
  thread_id: string;
  execution_status: string; // Graph execution state: 'user_feedback', 'running', 'finished'
  next_nodes: string[];
  plan: string;
  step_count: number;
  approval_status: string; // Agent approval state: 'approved', 'feedback', 'cancelled'
}