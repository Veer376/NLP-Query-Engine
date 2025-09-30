import { useState, type KeyboardEvent } from "react";
import { FiSend } from "react-icons/fi";
import ResultsView from "./ResultsView";
import MetricsDashboard from "./MetricsDashboard";
import type { ChatMessage } from "../state/types";

export type QueryPanelProps = {
  messages: ChatMessage[];
  disabled?: boolean;
  onSubmit: (query: string) => void;
  onBlocked?: () => void;
};

const QueryPanel = ({
  messages,
  disabled = false,
  onSubmit,
  onBlocked,
}: QueryPanelProps) => {
  const [query, setQuery] = useState("");
  const canSend = !disabled && query.trim().length > 0;

  const submit = () => {
    const value = query.trim();
    if (!value) return;
    onSubmit(value);
    setQuery("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) {
        submit();
      } else if (disabled) {
        onBlocked && onBlocked();
      }
    }
  };

  return (
    <section className="query-panel">
      <div className="chat-scroll">
        {messages.length === 0 ? (
          <p className="chat-empty-text">
            No conversations yet. Connect your data and ask a question to get
            started.
          </p>
        ) : (
          <ol className="chat-timeline">
            {messages.map((m: ChatMessage) => (
              <li key={m.id} className={`chat-bubble chat-${m.role}`}>
                {m.role === "user" ? (
                  <HumanMessage message={m} />
                ) : (
                  <SystemMessage message={m} />
                )}
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="composer" role="form" aria-label="Ask a question">
        <div className="composer-float">
          <div className="composer-input-wrap">
            <div className="composer-zoom">
              <textarea
                className="composer-input"
                placeholder={
                  disabled
                    ? "Connect a database to start querying"
                    : "Ask about employees, documents, or both"
                }
                rows={2}
                disabled={disabled}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onKeyDown}
              />
              <button
                type="button"
                className="composer-sendIcon"
                onClick={submit}
                disabled={!canSend}
                aria-label="Send"
                title="Send"
              >
                <FiSend />
              </button>
              {disabled && (
                <button
                  type="button"
                  className="composer-guard"
                  aria-label="Connect to the database first"
                  title="Connect to the database first"
                  onClick={() => onBlocked && onBlocked()}
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default QueryPanel;

const HumanMessage = ({ message }: { message: ChatMessage }) => {
  return (
    <article>
      <div className="chat-meta">
        <span className="chat-role">You</span>
        <time dateTime={new Date(message.createdAt).toISOString()}>
          {new Date(message.createdAt).toLocaleTimeString()}
        </time>
      </div>
      <p className="chat-text">{message.text}</p>
    </article>
  );
};

const SystemMessage = ({ message }: { message: ChatMessage }) => {
  return (
    <article>
      <div className="chat-meta">
        <span className="chat-role">System</span>
        <time dateTime={new Date(message.createdAt).toISOString()}>
          {new Date(message.createdAt).toLocaleTimeString()}
        </time>
      </div>
      {message.text && <p className="chat-text">{message.text}</p>}
      {message.result && (
        <div className="chat-results">
          <ResultsView result={message.result} />
          <MetricsDashboard
            totalMs={(message as any).performance_metrics?.total_ms}
            cacheHit={(message as any).performance_metrics?.cache_hit}
            sqlMs={(message as any).performance_metrics?.exec_ms}
            docSearchMs={(message as any).performance_metrics?.doc_search_ms}
            totalQueries={
              (message as any).performance_aggregates?.total_queries
            }
            cacheHitRate={
              (message as any).performance_aggregates?.cache_hit_rate
            }
            avgQueryTimeMs={
              (message as any).performance_aggregates?.avg_query_time_ms
            }
          />
        </div>
      )}
    </article>
  );
};

// MetricsStrip replaced by MetricsDashboard
