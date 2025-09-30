import { useMemo, useState } from "react";
import Modal from "./Modal";
import type { ResultPayload } from "../state/types";

interface ResultsViewProps {
  result?: ResultPayload;
}

const ResultsView = ({ result }: ResultsViewProps) => {
  if (!result) {
    return (
      <div className="results-placeholder">
        <p className="muted">No results yet.</p>
      </div>
    );
  }

  // Extract optional Confidence: XX% from summary for a small pill
  const match = /Confidence:\s*(\d+)%/.exec(result.summary || "");
  const confPct = match ? Number(match[1]) : undefined;

  const [open, setOpen] = useState(false);
  const [focusedDocId, setFocusedDocId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"sql" | "documents" | null>(null);

  const focusedDoc = useMemo(() => {
    if (!result?.documents || !focusedDocId) return null;
    return result.documents.find((d) => d.id === focusedDocId) || null;
  }, [result, focusedDocId]);

  const openFor = (mode: "sql" | "documents", docId?: string) => {
    setViewMode(mode);
    setFocusedDocId(docId ?? null);
    setOpen(true);
  };

  const downloadCsv = () => {
    if (!result.rows || result.rows.length === 0) return;
    const headers = Object.keys(result.rows[0]);
    const lines = [headers.join(",")].concat(
      result.rows.map((row) =>
        headers.map((h) => JSON.stringify(row[h] ?? "")).join(",")
      )
    );
    const blob = new Blob([lines.join("\n")], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "results.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadDocument = (docId?: string) => {
    const id = docId || focusedDocId;
    if (!id) return;
    const base =
      (import.meta as any).env?.VITE_API_BASE_URL || "http://localhost:8000";
    const link = document.createElement("a");
    link.href = `${String(base).replace(
      /\/$/,
      ""
    )}/api/download-document/${encodeURIComponent(id)}`;
    link.download = id;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <article className="results-card" aria-live="polite">
      <header className="results-header">
        <div className="results-badges">
          <span className={`badge badge-${result.type}`} title="Result type">
            {result.type.toUpperCase()}
          </span>
          {typeof confPct === "number" && !Number.isNaN(confPct) && (
            <span className="badge" title="Classifier confidence">
              {confPct}%
            </span>
          )}
          {result.documents && result.documents.length > 0 && (
            <span className="badge" title="Documents matched">
              DOCS: {result.documents.length}
            </span>
          )}
        </div>
        <p>{result.summary}</p>
      </header>
      {result.rows && result.rows.length > 0 && (
        <div
          className="results-table clickable"
          role="button"
          tabIndex={0}
          title="Open all rows"
          onClick={() => openFor("sql")}
          onKeyDown={(e) => {
            if (e.key === "Enter") openFor("sql");
          }}
        >
          <table>
            <thead>
              <tr>
                {Object.keys(result.rows[0]).map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.slice(0, 5).map((row, index) => (
                <tr key={index}>
                  {Object.entries(row).map(([column, value]) => (
                    <td key={column}>{String(value)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {result.documents && result.documents.length > 0 && (
        <div className="results-documents">
          {result.documents.slice(0, 3).map((document) => (
            <button
              key={document.id}
              className="document-card"
              onClick={() => openFor("documents", document.id)}
              title="Open document details"
            >
              <h4>{document.title}</h4>
              <p className="muted">{document.snippet}</p>
            </button>
          ))}
        </div>
      )}

      {/* Details Modal: shows all rows and all document matches */}
      <Modal
        title={
          viewMode === "documents" && focusedDoc
            ? `Document: ${focusedDoc.title}`
            : viewMode === "documents"
            ? "Documents"
            : "All rows"
        }
        isOpen={open}
        onClose={() => setOpen(false)}
      >
        {viewMode === "sql" && result.rows && result.rows.length > 0 && (
          <div
            className="results-table"
            style={{ maxHeight: 360, overflow: "auto" }}
          >
            <div className="results-actions" style={{ marginBottom: 8 }}>
              <button
                type="button"
                className="link-button"
                onClick={downloadCsv}
              >
                Download CSV
              </button>
            </div>
            <table>
              <thead>
                <tr>
                  {Object.keys(result.rows[0]).map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, index) => (
                  <tr key={index}>
                    {Object.entries(row).map(([column, value]) => (
                      <td key={column}>{String(value)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {viewMode === "documents" &&
          result.documents &&
          result.documents.length > 0 && (
            <div
              className="results-documents"
              style={{ maxHeight: 360, overflow: "auto" }}
            >
              {result.documents.map((document) => (
                <article
                  key={document.id}
                  className={`document-card${
                    focusedDocId === document.id ? " is-focused" : ""
                  }`}
                >
                  <h4>{document.title}</h4>
                  <p className="muted">
                    {document.snippet || "(no preview available)"}
                  </p>
                  <div className="results-actions">
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => downloadDocument(document.id)}
                    >
                      Download PDF
                    </button>
                  </div>
                </article>
              ))}
              {!focusedDoc && viewMode === "documents" && (
                <p className="muted" style={{ marginTop: 8 }}>
                  Showing top results returned by the backend. We’ll add
                  chunk-level views and full text retrieval.
                </p>
              )}
            </div>
          )}
      </Modal>
    </article>
  );
};

export default ResultsView;
