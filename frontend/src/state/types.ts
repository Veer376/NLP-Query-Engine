export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface SchemaTable {
  name: string;
  columns: string[];
}

export interface SchemaRelationship {
  sourceTable: string;
  targetTable: string;
  description?: string;
}

export interface SchemaSummary {
  tables: SchemaTable[];
  relationships: SchemaRelationship[];
}

// Raw backend schema (before adapting to UI summary)
export type BackendColumn = {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
};

export type BackendTable = {
  name: string;
  schema?: string;
  columns: BackendColumn[];
};

export interface BackendSchema {
  tables: BackendTable[];
  relationships: Array<{
    table: string;
    column: string;
    referred_table: string;
    referred_column: string;
    constraint_name?: string | null;
  }>;
}

export interface ConnectionState {
  status: ConnectionStatus;
  connectionString?: string;
  schema?: SchemaSummary;
  rawSchema?: BackendSchema;
  error?: string;
}

export type DocumentStatus = 'idle' | 'uploading' | 'processing' | 'complete' | 'error';

export interface DocumentRecord {
  id: string;
  name: string;
  size: number;
  status: DocumentStatus;
  progress: number;
  error?: string;
}

export type QueryResultType = 'sql' | 'documents' | 'hybrid';

export interface ResultPayload {
  type: QueryResultType;
  summary: string;
  rows?: Array<Record<string, unknown>>;
  documents?: Array<{ id: string; title: string; snippet: string }>;
}

export type ChatRole = 'user' | 'system';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  result?: ResultPayload;
  // Per-query metrics attached when message is a system result
  performance_metrics?: {
    total_ms?: number;
    cache_hit?: boolean;
    exec_ms?: number;
    doc_search_ms?: number;
  };
  // Aggregated metrics snapshot (optional)
  performance_aggregates?: {
    total_queries?: number;
    cache_hit_rate?: number;
    avg_query_time_ms?: number;
  };
  createdAt: number;
}

export interface AppState {
  connection: ConnectionState;
  documents: DocumentRecord[];
  chat: ChatMessage[];
  ui: {
    isDatabaseModalOpen: boolean;
    isDocumentModalOpen: boolean;
  };
}

export type AppAction =
  | { type: 'OPEN_DATABASE_MODAL' }
  | { type: 'CLOSE_DATABASE_MODAL' }
  | { type: 'OPEN_DOCUMENT_MODAL' }
  | { type: 'CLOSE_DOCUMENT_MODAL' }
  | { type: 'CONNECTION_REQUEST'; payload: { connectionString: string } }
  | { type: 'CONNECTION_SUCCESS'; payload: { schema: SchemaSummary; rawSchema: BackendSchema } }
  | { type: 'CONNECTION_FAILURE'; payload: { error: string } }
  | { type: 'RESET_CONNECTION' }
  | { type: 'DOCUMENT_UPLOAD_BEGIN'; payload: { records: DocumentRecord[] } }
  | { type: 'DOCUMENT_UPLOAD_PROGRESS'; payload: { id: string; progress: number } }
  | { type: 'DOCUMENT_UPLOAD_SUCCESS'; payload: { id: string } }
  | { type: 'DOCUMENT_UPLOAD_FAILURE'; payload: { id: string; error: string } }
  | { type: 'ADD_CHAT_MESSAGE'; payload: { message: ChatMessage } }
  | { type: 'RESET_CHAT' };
