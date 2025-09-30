export type ConnectResponse = {
  status: 'ok';
  schema: {
    tables: Array<{
      name: string;
      schema?: string;
      columns: Array<{
        name: string;
        type: string;
        nullable: boolean;
        primary_key: boolean;
      }>;
    }>;
    relationships: Array<{
      table: string;
      column: string;
      referred_table: string;
      referred_column: string;
      constraint_name?: string | null;
    }>;
  };
};

// Adapters to UI SchemaSummary
export function adaptSchemaToUi(resp: ConnectResponse['schema']) {
  return {
    tables: resp.tables.map((t) => ({
      name: t.name,
      columns: t.columns.map((c) => c.name),
    })),
    relationships: resp.relationships.map((r) => ({
      sourceTable: r.table,
      targetTable: r.referred_table,
      description: r.constraint_name || undefined,
    })),
  } as const;
}

export async function connectDatabase(baseUrl: string, connectionString: string) {
  const url = `${baseUrl.replace(/\/$/, '')}/api/connect-database`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    // Backend expects a JSON body: { connection_string: string }
    body: JSON.stringify({ connection_string: connectionString }),
  });
  if (!res.ok) {
    let msg = `Request failed with status ${res.status}`;
    try {
      const detail = await res.json();
      // FastAPI can return { detail: string } or { detail: [{loc, msg, type}, ...] }
      if (detail?.detail) {
        if (typeof detail.detail === 'string') msg = detail.detail;
        else if (Array.isArray(detail.detail)) msg = detail.detail.map((d: any) => d.msg).join('; ');
      }
    } catch {
      // ignore parse errors
    }
    throw new Error(String(msg));
  }
  const data = (await res.json()) as ConnectResponse;
  return { ui: adaptSchemaToUi(data.schema), raw: data.schema } as const;
}

export type QueryResponse = {
  query: string;
  ast?: {
    base_table: string;
    joins: string[];
    metrics: string[];
    filters: string[];
    group_by: string[];
    order_by: string[];
    limit: number;
  };
  sql?: string;
  query_type: 'sql' | 'docs' | 'documents' | 'hybrid';
  confidence?: number;
  classification_reasons?: string[];
  performance_metrics?: { exec_ms?: number; doc_search_ms?: number; total_ms?: number; cache_hit?: boolean };
  sources?: any[];
  executed: boolean;
  rows?: Array<Record<string, unknown>>;
  documents?: Array<{ id: string; title: string; snippet: string; score?: number; rank?: number }>;
  execution_skipped_reason?: string;
  execution_skipped_reason_sql?: string;
};

export async function runQuery(baseUrl: string, connectionString: string, query: string) {
  const url = `${baseUrl.replace(/\/$/, '')}/api/query`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ connection_string: connectionString, query }),
  });
  if (!res.ok) {
    let msg = `Request failed with status ${res.status}`;
    try {
      const detail = await res.json();
      if (detail?.detail) {
        if (typeof detail.detail === 'string') msg = detail.detail;
        else if (Array.isArray(detail.detail)) msg = detail.detail.map((d: any) => d.msg).join('; ');
      }
    } catch {}
    throw new Error(String(msg));
  }
  return (await res.json()) as QueryResponse;
}

export type QueryHistory = {
  status: 'ok';
  history: Array<{ query: string; cache_hit: boolean; total_ms: number; ts: number }>;
  metrics: {
    total_queries: number;
    cache_hits: number;
    cache_hit_rate: number;
    avg_query_time_ms: number;
  };
};

export async function getQueryHistory(baseUrl: string) {
  const url = `${baseUrl.replace(/\/$/, '')}/api/query/history`;
  const res = await fetch(url);
  if (!res.ok) {
    let msg = `Request failed with status ${res.status}`;
    try {
      const detail = await res.json();
      if (detail?.detail) msg = typeof detail.detail === 'string' ? detail.detail : JSON.stringify(detail.detail);
    } catch {}
    throw new Error(msg);
  }
  return (await res.json()) as QueryHistory;
}

// Document upload and ingestion status
export type UploadDocumentsResponse = { status: 'ok'; job_id: string };
export type IngestionStatus = {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'error';
  processed: number;
  total: number;
  progress: number; // 0-100
  errors: string[];
  index_ready: boolean;
  index_size: number;
  message?: string;
};

export async function uploadDocuments(baseUrl: string, files: FileList) {
  const url = `${baseUrl.replace(/\/$/, '')}/api/upload-documents`;
  const form = new FormData();
  Array.from(files).forEach((f) => form.append('files', f));
  const res = await fetch(url, { method: 'POST', body: form });
  if (!res.ok) {
    let msg = `Request failed with status ${res.status}`;
    try {
      const detail = await res.json();
      if (detail?.detail) msg = typeof detail.detail === 'string' ? detail.detail : JSON.stringify(detail.detail);
    } catch {}
    throw new Error(msg);
  }
  return (await res.json()) as UploadDocumentsResponse;
}

export async function getIngestionStatus(baseUrl: string, jobId: string) {
  const url = `${baseUrl.replace(/\/$/, '')}/api/ingestion-status/${jobId}`;
  const res = await fetch(url);
  if (!res.ok) {
    let msg = `Request failed with status ${res.status}`;
    try {
      const detail = await res.json();
      if (detail?.detail) msg = typeof detail.detail === 'string' ? detail.detail : JSON.stringify(detail.detail);
    } catch {}
    throw new Error(msg);
  }
  return (await res.json()) as IngestionStatus;
}
