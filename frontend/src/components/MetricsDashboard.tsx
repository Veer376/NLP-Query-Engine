/**
 * MetricsDashboard surfaces real-time performance and ingestion statistics for the query engine UI.
 */
import type { FC } from "react";

type MetricsDashboardProps = {
  // Per-query metrics
  totalMs?: number;
  cacheHit?: boolean;
  sqlMs?: number;
  docSearchMs?: number;
  // Aggregates (optional)
  totalQueries?: number;
  cacheHitRate?: number;
  avgQueryTimeMs?: number;
};

const MetricsDashboard: FC<MetricsDashboardProps> = ({
  totalMs,
  cacheHit,
  sqlMs,
  docSearchMs,
  totalQueries,
  cacheHitRate,
  avgQueryTimeMs,
}) => {
  return (
    <section aria-labelledby="metrics-dashboard-heading">
      <header>
        <h2 id="metrics-dashboard-heading">System metrics</h2>
      </header>
      <div className="metrics-strip" role="list">
        <span className="metric-pill" role="listitem">
          <strong>Query latency:</strong>&nbsp;
          {totalMs != null ? `${(totalMs / 1000).toFixed(1)} s` : "--"}
        </span>
        <span className="metric-pill" role="listitem">
          <strong>Cache:</strong>&nbsp;
          {cacheHit != null ? (cacheHit ? "hit" : "miss") : "--"}
        </span>
        <span className="metric-pill" role="listitem">
          <strong>SQL time:</strong>&nbsp;
          {sqlMs != null ? `${sqlMs.toFixed(1)} ms` : "--"}
        </span>
        <span className="metric-pill" role="listitem">
          <strong>Docs time:</strong>&nbsp;
          {docSearchMs != null ? `${docSearchMs.toFixed(1)} ms` : "--"}
        </span>
        {totalQueries != null && (
          <span className="metric-pill" role="listitem">
            <strong>Total queries:</strong>&nbsp;{totalQueries}
          </span>
        )}
        {cacheHitRate != null && (
          <span className="metric-pill" role="listitem">
            <strong>Cache hit rate:</strong>&nbsp;
            {Math.round(cacheHitRate * 100)}%
          </span>
        )}
        {avgQueryTimeMs != null && (
          <span className="metric-pill" role="listitem">
            <strong>Avg query time:</strong>&nbsp;
            {(avgQueryTimeMs / 1000).toFixed(2)} s
          </span>
        )}
      </div>
    </section>
  );
};

export default MetricsDashboard;
