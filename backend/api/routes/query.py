"""API routes for executing and tracking queries."""

from typing import Optional, Dict, Any, Tuple
import logging
import threading
import time
from collections import deque
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.services.query_engine import QueryEngine

logger = logging.getLogger("query")
router = APIRouter()


class QueryRequest(BaseModel):
    connection_string: str
    query: str
    page: int | None = None
    page_size: int | None = None


# --- Simple in-memory cache and history for demo ---
class _QueryHistory:
    def __init__(self, max_items: int = 100) -> None:
        self._items = deque(maxlen=max_items)
        self._lock = threading.Lock()
        self.total_queries = 0
        self.cache_hits = 0
        self.total_time_ms = 0.0

    def record(
        self, *, query: str, cache_hit: bool, total_ms: float, when: float
    ) -> None:
        with self._lock:
            self.total_queries += 1
            if cache_hit:
                self.cache_hits += 1
            self.total_time_ms += total_ms
            self._items.appendleft(
                {
                    "query": query,
                    "cache_hit": cache_hit,
                    "total_ms": total_ms,
                    "ts": when,
                }
            )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            avg_ms = (
                (self.total_time_ms / self.total_queries) if self.total_queries else 0.0
            )
            hit_rate = (
                (self.cache_hits / self.total_queries) if self.total_queries else 0.0
            )
            return {
                "history": list(self._items),
                "metrics": {
                    "total_queries": self.total_queries,
                    "cache_hits": self.cache_hits,
                    "cache_hit_rate": hit_rate,
                    "avg_query_time_ms": avg_ms,
                },
            }


class _QueryCache:
    def __init__(self, max_items: int = 200) -> None:
        self._data: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._order = deque()
        self._max = max_items
        self._lock = threading.Lock()

    def get(self, key: str) -> Dict[str, Any] | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            value, _ = item
            return value

    def set(self, key: str, value: Dict[str, Any]) -> None:
        with self._lock:
            if key in self._data:
                self._data[key] = (value, time.time())
                # move to front
                try:
                    self._order.remove(key)
                except ValueError:
                    pass
                self._order.appendleft(key)
            else:
                self._data[key] = (value, time.time())
                self._order.appendleft(key)
                if len(self._order) > self._max:
                    old = self._order.pop()
                    self._data.pop(old, None)


_history = _QueryHistory()
_cache = _QueryCache()


def _cache_key(
    connection_string: str, query: str, page: int | None, page_size: int | None
) -> str:
    # Normalize a minimal cache key
    try:
        from sqlalchemy.engine.url import make_url

        url = make_url(connection_string)
        driver = (url.drivername or "").split("+")[0]
        database = getattr(url, "database", None) or ""
        host = getattr(url, "host", None) or ""
        port = getattr(url, "port", None) or ""
        # omit password
        base = f"{driver}://{host}:{port}/{database}".lower()
    except Exception:
        base = connection_string
    return f"{base}|q={query}|p={page}|ps={page_size}"


@router.post("/api/query")
async def process_query(payload: QueryRequest):
    """
    Process natural language query using the provided connection.
    Returns: { query, ast, sql, query_type, performance_metrics, sources, executed, rows, execution_skipped_reason? }
    """
    if not payload.connection_string or not payload.query:
        raise HTTPException(
            status_code=400, detail="connection_string and query are required"
        )

    try:
        t0 = time.perf_counter()
        key = _cache_key(
            payload.connection_string, payload.query, payload.page, payload.page_size
        )
        cached = _cache.get(key)
        if cached is not None:
            total_ms = (time.perf_counter() - t0) * 1000.0
            # annotate a shallow copy with current timing and cache flag
            out = dict(cached)
            pm = dict(out.get("performance_metrics", {}))
            pm["total_ms"] = total_ms
            pm["cache_hit"] = True
            out["performance_metrics"] = pm
            _history.record(
                query=payload.query, cache_hit=True, total_ms=total_ms, when=time.time()
            )
            return out

        engine = QueryEngine(payload.connection_string)
        result = engine.process_query(
            payload.query, page=payload.page, page_size=payload.page_size
        )
        total_ms = (time.perf_counter() - t0) * 1000.0
        result.setdefault("performance_metrics", {})
        result["performance_metrics"]["total_ms"] = total_ms
        result["performance_metrics"]["cache_hit"] = False
        _cache.set(key, result)
        _history.record(
            query=payload.query, cache_hit=False, total_ms=total_ms, when=time.time()
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("/api/query failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"query_failed: {exc}") from exc


@router.get("/api/query/history")
async def get_query_history():
    """
    Get previous queries (for caching demo)
    """
    snap = _history.snapshot()
    return {"status": "ok", **snap}
