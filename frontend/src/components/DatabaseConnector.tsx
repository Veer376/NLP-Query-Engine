import { useMemo, useState, type FormEvent } from "react";
import type {
  ConnectionState,
  BackendSchema,
  BackendTable,
} from "../state/types";
import Modal from "./Modal";
import SchemaGraph from "./SchemaGraph";

interface DatabaseConnectorProps {
  connection: ConnectionState;
  onConnect: (connectionString: string) => Promise<void> | void;
  onReset: () => void;
  lastConnectMs?: number;
}

const DatabaseConnector = ({
  connection,
  onConnect,
  onReset,
  lastConnectMs,
}: DatabaseConnectorProps) => {
  const [connectionString, setConnectionString] = useState(
    connection.connectionString ?? ""
  );
  const [localError, setLocalError] = useState<string | undefined>(undefined);
  const rawSchema: BackendSchema | undefined = connection.rawSchema;
  const [columnsFor, setColumnsFor] = useState<BackendTable | null>(null);
  const [isGraphOpen, setGraphOpen] = useState(false);

  const tables: BackendTable[] = useMemo(
    () => rawSchema?.tables ?? [],
    [rawSchema]
  );

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!connectionString.trim()) {
      setLocalError("Connection string is required.");
      return;
    }
    setLocalError(undefined);
    try {
      await onConnect(connectionString.trim());
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unable to connect to database.";
      setLocalError(message);
    }
  };

  const handleReset = () => {
    setConnectionString("");
    setLocalError(undefined);
    onReset();
  };

  return (
    <section
      className="modal-section"
      aria-labelledby="database-connector-heading"
    >
      <header className="modal-header">
        <h2 id="database-connector-heading">Database connection</h2>
        <p className="muted">
          Provide a connection string to initiate schema discovery.
        </p>
      </header>
      <form
        className="vertical-form"
        onSubmit={handleSubmit}
        aria-label="Database connection form"
      >
        <label className="form-label" htmlFor="connection-string">
          Connection string
        </label>
        <input
          id="connection-string"
          name="connection-string"
          type="text"
          placeholder="postgresql://user:pass@host:port/database"
          className="text-input"
          value={connectionString}
          onChange={(event) => setConnectionString(event.target.value)}
          aria-invalid={Boolean(localError || connection.error)}
        />
        <div className="form-actions">
          <button
            type="submit"
            className="primary-button"
            disabled={connection.status === "connecting"}
          >
            {connection.status === "connecting"
              ? "Connecting…"
              : "Connect & analyze"}
          </button>
          <button type="button" className="ghost-button" onClick={handleReset}>
            Reset
          </button>
        </div>
        {(localError || connection.error) && (
          <p className="feedback feedback-error">
            {localError ?? connection.error}
          </p>
        )}
        {connection.status === "connected" && (
          <p className="feedback feedback-success">
            {lastConnectMs != null
              ? `Connected and extracted details in ${(
                  lastConnectMs / 1000
                ).toFixed(1)} sec.`
              : "Connection successful."}
          </p>
        )}
      </form>
      <details className="schema-collapsible" aria-live="polite">
        <summary className="schema-summary">
          <span>Tables</span>
          <span className="caret" aria-hidden>
            ▸
          </span>
        </summary>
        {tables.length === 0 ? (
          <p className="muted">No schema details available yet.</p>
        ) : (
          <ul className="schema-list">
            {tables.map((t) => (
              <li key={t.name}>
                <div className="schema-row">
                  <div className="row-name">{t.name}</div>
                  <div className="row-desc">—</div>
                  <div className="row-btn">
                    <button
                      type="button"
                      className="tiny-button"
                      onClick={() => setColumnsFor(t)}
                    >
                      {t.columns.length} columns
                    </button>
                  </div>
                  <div className="row-btn" />
                </div>
              </li>
            ))}
          </ul>
        )}
      </details>

      {/* Columns modal */}
      <Modal
        title="Columns"
        isOpen={!!columnsFor}
        onClose={() => setColumnsFor(null)}
      >
        {columnsFor && (
          <section className="modal-section">
            <header className="modal-header">
              <h2>Columns — {columnsFor.name}</h2>
            </header>
            <div
              className="results-table"
              style={{ maxHeight: "60vh", overflowY: "auto" }}
            >
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Nullable</th>
                    <th>Primary Key</th>
                  </tr>
                </thead>
                <tbody>
                  {columnsFor.columns.map((col) => (
                    <tr key={col.name}>
                      <td>{col.name}</td>
                      <td>{col.type}</td>
                      <td>{col.nullable ? "✓" : "✗"}</td>
                      <td>{col.primary_key ? "✓" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </Modal>

      {/* Schema Visualizer */}
      <div className="schema-preview" aria-live="polite">
        <h3 className="section-title">Schema Visualizer</h3>
        <p className="muted">
          Explore tables and relationships. Click a table to view its columns.
        </p>
        <div className="form-actions">
          <button
            type="button"
            className="ghost-button"
            title="Open schema graph"
            onClick={() => setGraphOpen(true)}
            disabled={!rawSchema || (rawSchema?.tables?.length ?? 0) === 0}
          >
            Open visualizer
          </button>
        </div>
      </div>

      {/* Graph modal */}
      <Modal
        title="Schema Graph"
        isOpen={isGraphOpen}
        onClose={() => setGraphOpen(false)}
      >
        {rawSchema ? (
          <SchemaGraph
            schema={rawSchema}
            onNodeClick={(t) => {
              setColumnsFor(t);
              setGraphOpen(false);
            }}
            height={520}
          />
        ) : (
          <p className="muted">No schema available.</p>
        )}
      </Modal>
    </section>
  );
};

export default DatabaseConnector;
