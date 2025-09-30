import { useMemo, useState } from "react";
import "./App.css";
import DatabaseConnector from "./components/DatabaseConnector";
import DocumentUploader from "./components/DocumentUploader";
import Modal from "./components/Modal";
import {
  useAppActions,
  useAppState,
  createChatMessage,
} from "./state/AppContext";
import type { ResultPayload } from "./state/types";
import {
  connectDatabase as apiConnect,
  runQuery,
  uploadDocuments,
  getIngestionStatus,
  getQueryHistory,
} from "./api";
import { FiDatabase, FiFileText } from "react-icons/fi";
import QueryPanel from "./components/QueryPanel";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const App = () => {
  const state = useAppState();
  const actions = useAppActions();
  const [lastConnectMs, setLastConnectMs] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [ingestAggregate, setIngestAggregate] = useState<{
    processed: number;
    total: number;
    percent: number;
  } | null>(null);

  const canQuery = state.connection.status === "connected";

  const handleConnect = async (connectionString: string) => {
    actions.requestConnection(connectionString);
    try {
      const t0 = performance.now();
      const { ui, raw } = await apiConnect(API_BASE, connectionString);
      actions.connectionSuccess(ui as any, raw as any);
      const ms = performance.now() - t0;
      setLastConnectMs(ms);
      const secs = (ms / 1000).toFixed(1);
      setToast(`Connected and extracted details in ${secs} sec`);
      window.setTimeout(() => setToast(null), 2200);
      actions.closeDatabaseModal();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to connect to database";
      actions.connectionFailure(message);
      throw err;
    }
  };

  const handleResetConnection = () => {
    actions.resetConnection();
  };

  const handleUploadDocuments = async (files: FileList) => {
    const records = Array.from(files).map((file) => ({
      id: crypto.randomUUID(),
      name: file.name,
      size: file.size,
      status: "uploading" as const,
      progress: 5,
    }));
    actions.beginDocumentUpload(records);

    try {
      const { job_id } = await uploadDocuments(API_BASE, files);
      // initialize aggregate using client-side knowledge; will be updated from server
      setIngestAggregate({ processed: 0, total: records.length, percent: 5 });
      const poll = async () => {
        try {
          const s = await getIngestionStatus(API_BASE, job_id);
          const pct = Math.max(5, Math.min(98, s.progress));
          setIngestAggregate({
            processed: s.processed,
            total: s.total,
            percent: pct,
          });
          records.forEach((r) => actions.documentUploadProgress(r.id, pct));
          if (s.status === "completed") {
            records.forEach((r) => actions.documentUploadSuccess(r.id));
            setIngestAggregate(null);
            return;
          }
          if (s.status === "error") {
            records.forEach((r) =>
              actions.documentUploadFailure(
                r.id,
                s.message || "ingestion_error"
              )
            );
            setIngestAggregate(null);
            return;
          }
          setTimeout(poll, 800);
        } catch (err) {
          const msg = err instanceof Error ? err.message : "status_poll_failed";
          records.forEach((r) => actions.documentUploadFailure(r.id, msg));
          setIngestAggregate(null);
        }
      };
      setTimeout(poll, 600);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "upload_failed";
      records.forEach((r) => actions.documentUploadFailure(r.id, msg));
      setIngestAggregate(null);
    }
  };

  const handleQuerySubmit = async (query: string) => {
    const userMessage = createChatMessage({ role: "user", text: query });
    actions.addChatMessage(userMessage);

    try {
      const conn = state.connection;
      if (!conn.connectionString) {
        throw new Error(
          "No connection string available. Connect a database first."
        );
      }
      const res = await runQuery(API_BASE, conn.connectionString, query);

      // Normalize type name for UI
      const qtype = (
        res.query_type === "docs" ? "documents" : res.query_type
      ) as "sql" | "documents" | "hybrid";

      const rows = Array.isArray(res.rows) ? res.rows : [];
      const docs = Array.isArray(res.documents) ? res.documents : [];

      const metrics: string[] = [];
      if (typeof res.confidence === "number")
        metrics.push(`Confidence: ${(res.confidence * 100).toFixed(0)}%`);
      if (res.performance_metrics?.exec_ms)
        metrics.push(`SQL: ${res.performance_metrics.exec_ms.toFixed(1)} ms`);
      if (res.performance_metrics?.doc_search_ms)
        metrics.push(
          `Docs: ${res.performance_metrics.doc_search_ms.toFixed(1)} ms`
        );
      if (res.execution_skipped_reason)
        metrics.push(`Reason: ${res.execution_skipped_reason}`);

      // Prepend headline timing per assignment: "Query took Xs (cache hit/miss)"
      const tookMs = res.performance_metrics?.total_ms ?? 0;
      const took = (tookMs / 1000).toFixed(1);
      const hitMiss = res.performance_metrics?.cache_hit
        ? "cache hit"
        : "cache miss";
      const summary = [`Query took ${took}s (${hitMiss})`, ...metrics].join(
        " | "
      );
      const preface = res.sql
        ? `SQL: ${res.sql}`
        : res.ast
        ? `AST: ${JSON.stringify(res.ast)}`
        : "";

      const result: ResultPayload = {
        type: qtype as ResultPayload["type"],
        summary,
        rows: qtype !== "documents" ? rows : undefined,
        documents:
          qtype !== "sql"
            ? docs.map((d) => ({
                id: d.id,
                title: d.title,
                snippet: d.snippet,
              }))
            : undefined,
      };

      // Fetch aggregate metrics snapshot (optional)
      let aggregates: any = undefined;
      try {
        const snap = await getQueryHistory(API_BASE);
        aggregates = {
          total_queries: snap.metrics.total_queries,
          cache_hit_rate: snap.metrics.cache_hit_rate,
          avg_query_time_ms: snap.metrics.avg_query_time_ms,
        };
      } catch {}

      const systemMessage = createChatMessage({
        role: "system",
        text: preface,
        result,
        performance_metrics: res.performance_metrics,
        performance_aggregates: aggregates,
      });
      actions.addChatMessage(systemMessage);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Query failed";
      const errorMessage = createChatMessage({
        role: "system",
        text: `Error: ${message}`,
      });
      actions.addChatMessage(errorMessage);
    }
  };

  const chatMessages = useMemo(() => state.chat, [state.chat]);

  const onBlocked = () => {
    setToast("Connect to the database first");
    window.setTimeout(() => setToast(null), 1800);
  };

  return (
    <div className="app-shell">
      <div className="floating-actions-right" aria-label="Global actions">
        <span
          className={`status-dot ${state.connection.status}`}
          title={`Status: ${state.connection.status}`}
          aria-hidden
        />
        <button
          type="button"
          className="icon-button"
          aria-label="Connect database"
          title="Connect database"
          onClick={actions.openDatabaseModal}
        >
          <FiDatabase />
        </button>
        <button
          type="button"
          className="icon-button"
          aria-label="Upload documents"
          title="Upload documents"
          onClick={actions.openDocumentModal}
        >
          <FiFileText />
        </button>
      </div>

      <div className="floating-left-label" aria-hidden="true">
        Ekam Apps
      </div>

      <main className="chat-body" aria-label="Conversation">
        <QueryPanel
          messages={chatMessages}
          disabled={!canQuery}
          onSubmit={handleQuerySubmit}
          onBlocked={onBlocked}
        />
      </main>

      <Modal
        title="Database connection"
        isOpen={state.ui.isDatabaseModalOpen}
        onClose={actions.closeDatabaseModal}
      >
        <DatabaseConnector
          connection={state.connection}
          onConnect={handleConnect}
          onReset={handleResetConnection}
          lastConnectMs={lastConnectMs ?? undefined}
        />
      </Modal>

      <Modal
        title="Document ingestion"
        isOpen={state.ui.isDocumentModalOpen}
        onClose={actions.closeDocumentModal}
      >
        <DocumentUploader
          documents={state.documents}
          onUpload={handleUploadDocuments}
          aggregateProgress={ingestAggregate ?? undefined}
        />
      </Modal>
      {toast && (
        <div className="toast toast-info" role="status" aria-live="polite">
          {toast}
        </div>
      )}
    </div>
  );
};

export default App;
