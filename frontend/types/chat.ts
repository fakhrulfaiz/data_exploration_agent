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
    internalTools?: Array<{
      name: string;
      status: 'completed' | 'running' | 'error';
    }>;
    generatedContent?: {
      type: 'sql' | 'code' | 'text';
      content: string;
      editable: boolean;
    };
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
  dynamic_plan?: {
    query: string;
    overall_strategy: string;
    steps: Array<{
      step_number: number;
      goal: string;
      tool_options: Array<{
        tool_name: string;
        use_case: string;
        priority: number;
      }>;
      context_requirements?: string;
    }>;
    completed_steps?: string[];
    intent?: {
      main_intent: string;
      sub_intents: string[];
    };
  };
}

export interface ErrorContent {
  what_happened: string;
  why_it_happened: string;
  what_was_attempted: string;
  alternative_suggestions: string[];
  user_action_needed: string;
  technical_details?: string;
}

export interface ExplanationContent {
  decision: string;
  reasoning?: string;
  tool_justification?: string;
  contrastive_explanation?: string;
  data_evidence?: string;
  policy_audits?: Array<{
    policy_name: string;
    passed: boolean;
    message: string;
    severity: 'info' | 'warning' | 'error';
  }>;
  counterfactual?: string | null;
}

export interface ReasoningChainContent {
  steps: Array<{
    step_number: number;
    tool_used: string;
    what_happened: string;
    key_finding?: string | null;
  }>;
}

export interface ContentBlock {
  id: string;
  type: 'text' | 'tool_calls' | 'explorer' | 'visualizations' | 'plan' | 'error' | 'explanation' | 'reasoning_chain';
  needsApproval?: boolean;
  messageStatus?: 'pending' | 'approved' | 'rejected' | 'error' | 'timeout';
  metadata?: any;
  data: TextContent | ToolCallsContent | ExplorerContent | VisualizationsContent | PlanContent | ErrorContent | ExplanationContent | ReasoningChainContent;
}

export interface Message {
  message_id: string; // Backend UUID message identifier
  sender: 'user' | 'assistant';
  // Content is always an array of content blocks
  content: ContentBlock[];
  timestamp: Date;
  isStreaming?: boolean;
  threadId?: string;
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
      internalTools?: Array<{
        name: string;
        status: 'completed' | 'running' | 'error';
      }>;
      generatedContent?: {
        type: 'sql' | 'code' | 'text';
        content: string;
        editable: boolean;
      };
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

export const createPlanBlock = (id: string, plan: string, needsApproval: boolean): ContentBlock => ({
  id,
  type: 'plan',
  needsApproval,
  data: { plan }
});

export const isPlanBlock = (block: ContentBlock): block is ContentBlock & { data: PlanContent } =>
  block.type === 'plan';

export const createErrorBlock = (id: string, errorExplanation: ErrorContent): ContentBlock => ({
  id,
  type: 'error',
  needsApproval: false,
  data: errorExplanation
});

export const isErrorBlock = (block: ContentBlock): block is ContentBlock & { data: ErrorContent } =>
  block.type === 'error';

export const createExplanationBlock = (id: string, explanationData: ExplanationContent): ContentBlock => ({
  id,
  type: 'explanation',
  needsApproval: false,
  data: explanationData
});

export const isExplanationBlock = (block: ContentBlock): block is ContentBlock & { data: ExplanationContent } =>
  block.type === 'explanation';

export const createReasoningChainBlock = (id: string, chainData: ReasoningChainContent): ContentBlock => ({
  id,
  type: 'reasoning_chain',
  needsApproval: false,
  data: chainData
});

export const isReasoningChainBlock = (block: ContentBlock): block is ContentBlock & { data: ReasoningChainContent } =>
  block.type === 'reasoning_chain';

// Response object that handlers can return
export interface HandlerResponse {
  message: string;
  needsApproval?: boolean;
  explorerData?: any;
  visualizations?: any[];
  checkpoint_id?: string; // Add checkpoint ID for both explorer and visualization messages
  response_type?: 'answer' | 'replan' | 'cancel';  // Type of response from backend
  backendMessageId?: string; // Backend-generated UUID message ID for assistant messages
  explorerMessageId?: string; // Backend-generated message ID for explorer messages
  visualizationMessageId?: string; // Backend-generated message ID for visualization messages
  // New streaming properties
  isStreaming?: boolean;
  streamingHandler?: (
    streamingMessageId: string,
    updateContentCallback: (id: string, contentBlocks?: ContentBlock[]) => void,
    onStatus?: (status: 'user_feedback' | 'finished' | 'running' | 'error' | 'tool_call' | 'tool_result' | 'completed_payload' | 'visualizations_ready' | 'content_block' | 'graph_node', eventData?: string, responseType?: 'answer' | 'replan' | 'cancel') => void
  ) => Promise<void>;
}


export interface ChatComponentProps {
  onSendMessage: (message: string, messageHistory: Message[], options?: { usePlanning?: boolean; useExplainer?: boolean; attachedFiles?: File[] }) => Promise<HandlerResponse>;
  onApprove?: (messageId: string | undefined, content: string, message: Message) => Promise<HandlerResponse | void> | HandlerResponse | void;
  onFeedback?: (messageId: string | undefined, content: string, message: Message) => Promise<HandlerResponse | void> | HandlerResponse | void;
  onCancel?: (messageId: string | undefined, content: string, message: Message) => Promise<string> | string;
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
  onDataFrameDetected?: (dfId: string) => void; // Callback when df_id is detected in tool output
  onCancelStream?: () => Promise<void>; // Callback to cancel ongoing stream
  onToggleGraphPanel?: () => void; // Callback to toggle graph flow panel
  graphPanelOpen?: boolean; // Whether graph panel is currently open
  graphStructure?: any; // Graph structure data for visualization (GraphStructure from types/graph.ts)
}

export interface MessageComponentProps {
  message: Message;
  onRetry?: (messageId: string) => void;
  showIcon?: boolean; // Whether to show the assistant icon (for grouping consecutive messages)
  onApproveBlock?: (blockId: string) => void; // Handler for approving a block
  onRejectBlock?: (blockId: string) => void; // Handler for rejecting a block
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

export interface ToolCall {
  tool_call_id: string;
  tool_name: string;
  input: string;  // JSON string
  output?: string;
}

export interface StepExplanation {
  id: number;
  plan_step_index: number;
  decision: string;
  reasoning: string;
  timestamp: string;
  tool_justification?: string;
  data_evidence?: string;
  counterfactual?: string;
  tool_calls: ToolCall[];
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

export interface ActionRequest {
  action: string;  // Tool name (e.g., "sql_db_query")
  args: Record<string, any>;  // Tool arguments
}

/**
 * Configuration for human interrupt
 */
export interface HumanInterruptConfig {
  allow_ignore: boolean;   // Can user reject?
  allow_respond: boolean;  // Can user provide text response?
  allow_edit: boolean;     // Can user edit arguments?
  allow_accept: boolean;   // Can user approve?
}

/**
 * Human interrupt request from backend
 */
export interface HumanInterrupt {
  action_request: ActionRequest;
  config: HumanInterruptConfig;
  description: string;  // User-friendly description
}

/**
 * Human response to interrupt
 */
export interface HumanResponse {
  type: 'accept' | 'ignore' | 'edit' | 'response';
  args: null | string | ActionRequest;  // Depends on type
}

/**
 * Interrupt wrapper from LangGraph
 */
export interface InterruptData {
  value: HumanInterrupt;
}

/**
 * Extended graph response with interrupt support
 */
export interface GraphResponseWithInterrupt extends GraphResponse {
  __interrupt__?: InterruptData[];
}