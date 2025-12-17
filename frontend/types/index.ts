/**
 * TypeScript Type Definitions
 * Matches backend Pydantic schemas
 */

// ==================== Base Response Types ====================

export interface ErrorInfo {
    code: string;
    message: string;
}

export interface BaseResponse<T = any> {
    status?: 'success' | 'error';
    data?: T;
    message: string;
    errors?: ErrorInfo[];
}

export interface SuccessResponse<T = any> extends BaseResponse<T> {
    status: 'success';
    data: T;
}

// ==================== Enums ====================

export enum MessageStatus {
    PENDING = 'pending',
    APPROVED = 'approved',
    REJECTED = 'rejected',
    ERROR = 'error',
    TIMEOUT = 'timeout',
}

export enum MessageType {
    MESSAGE = 'message',
    EXPLORER = 'explorer',
    VISUALIZATION = 'visualization',
    FEEDBACK = 'feedback',
}

export enum ExecutionStatus {
    PENDING = 'pending',
    RUNNING = 'running',
    FINISHED = 'finished',
    ERROR = 'error',
    USER_FEEDBACK = 'user_feedback',
}

export enum ApprovalStatus {
    APPROVED = 'approved',
    FEEDBACK = 'feedback',
    REJECTED = 'rejected',
}

// ==================== Conversation Types ====================

export interface CreateConversationRequest {
    title: string;
    initial_message?: string;
}

export interface UpdateTitleRequest {
    title: string;
}

export interface ConversationSummary {
    thread_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    message_count: number;
    last_message_preview?: string;
}

export interface ConversationData {
    thread_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    messages: any[];
    message_count: number;
}

export interface ConversationResponse extends BaseResponse<ConversationData> { }

export interface ConversationListData {
    conversations: ConversationSummary[];
    total: number;
}

export interface ConversationListResponse extends BaseResponse<ConversationListData> { }

// ==================== Message Management Types ====================

export interface MessageStatusUpdateRequest {
    message_status?: MessageStatus;
}

export interface BlockStatusUpdateRequest {
    needsApproval?: boolean;
    messageStatus?: MessageStatus;
}

export interface MessageStatusInfo {
    message_id: number;
    sender: string;
    timestamp: string;
    message_status: MessageStatus;
    message_type: MessageType;
    checkpoint_id?: string;
    has_content_blocks: boolean;
}

export interface MessageStatusListData {
    thread_id: string;
    message_count: number;
    messages: MessageStatusInfo[];
}

export interface MessageStatusListResponse extends BaseResponse<MessageStatusListData> { }

// ==================== Checkpoint Types ====================

export interface CheckpointSummary {
    checkpoint_id: string;
    thread_id: string;
    timestamp: string;
    message_type?: string;
    message_id: number;
    query?: string;
}

export interface CheckpointListData {
    checkpoints: CheckpointSummary[];
    total: number;
}

export interface CheckpointListResponse extends BaseResponse<CheckpointListData> { }

// ==================== Data Context Types ====================

export interface DataContext {
    df_id: string;
    sql_query: string;
    columns: string[];
    shape: number[];
    created_at: string;
    expires_at: string;
    metadata: Record<string, any>;
}

export interface RestoreConversationData extends ConversationData {
    data_context?: DataContext;
}

export interface RestoreConversationResponse extends BaseResponse<RestoreConversationData> { }

// ==================== Agent Types ====================

export interface AgentRequest {
    message: string;
    session_id?: string;
}

export interface AgentExecutionData {
    messages: any[];
    thread_id: string;
    state?: any;
}

export interface AgentResponse extends BaseResponse<AgentExecutionData> { }

export interface ThreadStateData {
    thread_id: string;
    state: any;
    next: string[];
    config: any;
    metadata: any;
    created_at?: string;
}

export interface StateResponse extends BaseResponse<ThreadStateData> { }

export interface StateUpdateRequest {
    state_updates: Record<string, any>;
}

export interface BulkDeleteRequest {
    thread_ids: string[];
}

export interface BulkDeleteData {
    results: Record<string, boolean>;
    successful: number;
    failed: number;
}

export interface BulkDeleteResponse extends BaseResponse<BulkDeleteData> { }

export interface CleanupData {
    deleted_count: number;
    threads_affected: number;
    oldest_deleted?: string;
}

export interface CleanupResponse extends BaseResponse<CleanupData> { }

// ==================== Data Types ====================

export interface DataFramePreviewData {
    df_id: string;
    columns: string[];
    total_rows: number;
    preview_rows: number;
    data: Record<string, any>[];
    metadata?: Record<string, any>;
}

export interface DataFramePreviewResponse extends BaseResponse<DataFramePreviewData> { }

export interface RecreateDataFrameRequest {
    thread_id: string;
    sql_query: string;
}

export interface RecreateDataFrameData extends DataFramePreviewData { }

export interface RecreateDataFrameResponse extends BaseResponse<RecreateDataFrameData> { }

// ==================== Graph Types ====================

export interface StartGraphRequest {
    thread_id?: string;
    human_request: string;
    use_planning?: boolean;
    use_explainer?: boolean;
}

export interface ResumeGraphRequest {
    thread_id: string;
    review_action: ApprovalStatus;
    human_comment?: string;
}

export interface GraphData {
    thread_id: string;
    run_status: string;
    assistant_response?: string;
    query?: string;
    plan?: string;
    steps?: any[];
    final_result?: any;
    total_time?: number;
    overall_confidence?: number;
    assistant_message_id?: number;
    checkpoint_id?: string;
    error?: string;
    response_type?: 'answer' | 'replan' | 'cancel';
    visualizations?: any[];
}

export interface GraphResponse extends BaseResponse<GraphData> { }

// ==================== SSE Streaming Types ====================

export interface StreamCallbacks {
    onMessage: (data: any) => void;
    onError: (error: Error) => void;
    onComplete: () => void;
}

export interface ContentBlock {
    id: string;
    type: 'text' | 'tool_calls' | 'explorer' | 'visualizations';
    needsApproval?: boolean;
    data: any;
    sequence?: number;
}

export interface ToolCall {
    name: string;
    input: Record<string, any>;
    output?: any;
    status?: 'approved' | 'error';
    error?: string;
}
