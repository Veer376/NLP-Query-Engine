"""Service responsible for dynamic schema discovery and natural language mapping."""

from typing import Dict, List, Any, Tuple
import logging
from time import perf_counter

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import inspect
import time
import logging
import re

logger = logging.getLogger("schema_discovery")


class SchemaDiscovery:
    """Encapsulates schema analysis logic for arbitrary employee databases."""

    def __init__(self):
        # Legacy single schema (kept for compatibility where needed)
        self.schema = None
        # New: cache per connection string with timestamp for basic TTL invalidation
        self._cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._lock = None  # lazy-init threading.Lock to avoid import at module load

    SUPPORTED_SCHEMES = ("postgresql", "postgres", "sqlite")

    def _validate_connection_string(self, connection_string: str) -> None:
        """Raise ValueError if the URL scheme is unsupported."""
        # SQLAlchemy can parse the dialect out of the URL
        try:
            from sqlalchemy.engine.url import make_url

            url = make_url(connection_string)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid connection string: {exc}") from exc

        if url.drivername.split("+")[0] not in self.SUPPORTED_SCHEMES:
            raise ValueError(
                f"Unsupported database; supported: {', '.join(self.SUPPORTED_SCHEMES)}"
            )
        # Minimal sanity check for common mistake: '@' leaking into host segment
        try:
            host = getattr(url, "host", None)
            if isinstance(host, str) and "@" in host:
                raise ValueError(
                    "Invalid host: '@' found in host segment. If '@' is part of the password, URL-encode it as '%40'."
                )
        except Exception:
            # Best-effort guard; ignore if url lacks host attribute (e.g., sqlite)
            pass

    def _connect(self, connection_string: str) -> Engine:
        """Create a SQLAlchemy engine and test connectivity."""
        t0 = perf_counter()
        engine = create_engine(connection_string, pool_pre_ping=True)
        # Simple connectivity check
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        t1 = perf_counter()
        logging.info("[schema] connect ok in %.3fs", (t1 - t0))
        return engine

    def _cache_key(self, connection_string: str) -> str:
        """Build a canonical cache key from a DB URL, ignoring password.

        This allows schema reuse across sessions even if credentials rotate.
        """
        try:
            from sqlalchemy.engine.url import make_url

            url = make_url(connection_string)
            driver = (url.drivername or "").split("+")[0]
            database = getattr(url, "database", None) or ""
            host = getattr(url, "host", None) or ""
            port = getattr(url, "port", None) or ""
            username = getattr(url, "username", None) or ""  # optionally include
            # For sqlite, host may be empty; database carries file path or ':memory:'
            return f"{driver}://{username}@{host}:{port}/{database}".lower()
        except Exception:
            # Fallback: use the raw string (may create more cache entries)
            return connection_string

    def analyze_database(
        self, connection_string: str, *, ttl_seconds: int | None = None
    ) -> Dict[str, Any]:
        """
        Connect to the database and discover:
        - Table names
        - Columns and data types
        - Foreign key relationships

        Returns a dict:
        {
          'tables': [
             {'name': str, 'columns': [{'name': str, 'type': str, 'nullable': bool, 'primary_key': bool}]}
          ],
          'relationships': [
             {'table': str, 'column': str, 'referred_table': str, 'referred_column': str, 'constraint_name': str|None}
          ]
        }
        """
        # Fast path: per-connection cache
        if self._lock is None:
            import threading

            self._lock = threading.Lock()
        now = time.time()
        key = self._cache_key(connection_string)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                schema_cached, ts = cached
                if ttl_seconds is None or (now - ts) < ttl_seconds:
                    # also update legacy field for downstream callers
                    self.schema = schema_cached
                    return schema_cached

        if self.schema is None:
            logger.info("No previously cached schema; performing discovery")

        self._validate_connection_string(connection_string)
        try:
            engine = self._connect(connection_string)
            logger.info("Engine created")

        except SQLAlchemyError as exc:
            # Re-raise with a clearer message for the API layer to format
            raise ConnectionError(f"Database connection failed: {exc}") from exc

        start = time.time()
        inspector = inspect(engine)
        logger.info("Connected and inspector created in %.3fs", time.time() - start)
        # Determine schemas to inspect
        # - PostgreSQL: enumerate all non-system schemas (public + user-defined)
        # - SQLite: use default (schema=None)
        try:
            dialect = (inspector.dialect.name or "").lower()
            if dialect in ("postgresql", "postgres"):
                try:
                    all_schemas = inspector.get_schema_names()
                except Exception:
                    all_schemas = ["public"]
                # Filter out system schemas to reduce noise
                system_schemas = {
                    "pg_catalog",
                    "information_schema",
                    "pg_toast",
                    "pg_temp_1",
                    "pg_toast_temp_1",
                }
                schemas = [s for s in all_schemas if s not in system_schemas]
                if not schemas:
                    schemas = ["public"]
            else:
                # SQLite (and others we don't explicitly support here) don't use named schemas
                schemas = [None]
        except Exception:
            schemas = [None]

        tables_out: List[Dict[str, Any]] = []
        rels_out: List[Dict[str, Any]] = []

        t_discovery_start = perf_counter()
        for schema_name in schemas:
            t_tables_start = perf_counter()
            table_names = inspector.get_table_names(schema=schema_name)
            logging.info(
                "[schema] listed %d tables in schema '%s' in %.3fs",
                len(table_names),
                schema_name or "default",
                perf_counter() - t_tables_start,
            )
            for table in table_names:
                t_cols_start = perf_counter()
                # Columns
                cols = inspector.get_columns(table, schema=schema_name)
                pk = set(
                    inspector.get_pk_constraint(table, schema=schema_name).get(
                        "constrained_columns", []
                    )
                    or []
                )
                columns = [
                    {
                        "name": c.get("name"),
                        "type": str(c.get("type")),
                        "nullable": bool(c.get("nullable", True)),
                        "primary_key": c.get("name") in pk,
                    }
                    for c in cols
                ]
                logging.info(
                    "[schema] columns for %s.%s: %d cols in %.3fs",
                    schema_name or "default",
                    table,
                    len(columns),
                    perf_counter() - t_cols_start,
                )

                # Build explicit identifiers
                fq_name = f"{schema_name}.{table}" if schema_name else table
                base_name = table  # schema-less base name for display/search

                tables_out.append(
                    {
                        "name": fq_name,  # keep existing 'name' as fully-qualified for backward-compat
                        "fq_name": fq_name,
                        "base_name": base_name,
                        "schema": schema_name or "public",
                        "columns": columns,
                    }
                )

                # Foreign keys
                t_fk_start = perf_counter()
                fks = inspector.get_foreign_keys(table, schema=schema_name)
                for fk in fks:
                    referred_table = fk.get("referred_table")
                    referred_schema = fk.get("referred_schema")
                    for lc, rc in zip(
                        fk.get("constrained_columns", []),
                        fk.get("referred_columns", []),
                    ):
                        rels_out.append(
                            {
                                "table": (
                                    f"{schema_name}.{table}" if schema_name else table
                                ),
                                "column": lc,
                                "referred_table": (
                                    f"{referred_schema}.{referred_table}"
                                    if referred_schema
                                    else referred_table
                                ),
                                "referred_column": rc,
                                "constraint_name": fk.get("name"),
                            }
                        )
                logging.info(
                    "[schema] fks for %s.%s: %d rels in %.3fs",
                    schema_name or "default",
                    table,
                    len(rels_out),
                    perf_counter() - t_fk_start,
                )

        logging.info(
            "[schema] discovery complete: %d tables, %d relationships in %.3fs",
            len(tables_out),
            len(rels_out),
            perf_counter() - t_discovery_start,
        )

        schema_built = {"tables": tables_out, "relationships": rels_out}
        # Save in both legacy and cache for compatibility and reuse
        with self._lock:
            self.schema = schema_built
            self._cache[key] = (schema_built, time.time())
        return schema_built

    def _norm(self, s: str) -> str:
        return s.lower().strip()

    def _tokens(self, text: str) -> List[str]:
        return [t.lower() for t in re.findall(r"[A-Za-z0-9_]+", text)]

    def _is_numeric_type(self, db_type: str) -> bool:
        t = (db_type or "").upper()
        return any(k in t for k in ["INT", "DEC", "NUM", "FLOAT", "REAL", "DOUBLE"])

    def _base_name(self, table_name: str) -> str:
        # Split schema.table -> table
        return table_name.split(".")[-1]

    def map_natural_language_to_schema(
        self, query: str, schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Input schema shape:
          { "tables": [{name, schema, columns:[{name,type,nullable,primary_key}]}],
            "relationships": [{table, column, referred_table, referred_column, constraint_name}] }

        Output AST shape:
          { base_table, joins: [table], metrics: [expr], filters: [expr], group_by: [], order_by: [], limit: 100 }
        """
        q_tokens = self._tokens(query)

        # 1) Build indexes
        tables: List[Dict[str, Any]] = schema.get("tables", []) or []
        rels: List[Dict[str, Any]] = schema.get("relationships", []) or []

        table_by_name: Dict[str, Dict[str, Any]] = {}
        table_name_tokens: Dict[str, set] = {}
        for t in tables:
            name = t["name"]
            table_by_name[name] = t
            base = self._base_name(name)
            toks = set(self._tokens(base)) | set(self._tokens(name))
            table_name_tokens[name] = toks

        # Column to (table, column_info)
        col_index: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        # Table -> set of columns
        table_columns: Dict[str, List[Dict[str, Any]]] = {}
        for t in tables:
            cols = t.get("columns", []) or []
            table_columns[t["name"]] = cols
            for c in cols:
                col_index[c["name"].lower()] = (t["name"], c)

        # Relationship adjacency (both directions)
        neighbors: Dict[str, set] = {t["name"]: set() for t in tables}
        for r in rels:
            a = r["table"]
            b = r["referred_table"]
            if a in neighbors:
                neighbors[a].add(b)
            if b in neighbors:
                neighbors[b].add(a)

        # 2) Detect base table:
        #    a) direct name/token mention
        #    b) most column mentions
        base_table = None
        # a) table name mention
        for name, toks in table_name_tokens.items():
            if any(tok in q_tokens for tok in toks):
                base_table = name
                break

        # b) most column mentions
        if not base_table:
            column_hits_per_table: Dict[str, int] = {t["name"]: 0 for t in tables}
            for token in q_tokens:
                if token in col_index:
                    tname, _ = col_index[token]
                    column_hits_per_table[tname] += 1
            if column_hits_per_table:
                base_table = max(
                    column_hits_per_table, key=lambda k: column_hits_per_table[k]
                )
                if column_hits_per_table[base_table] == 0:
                    base_table = None

        if not base_table and tables:
            # last resort: pick first table (keeps function robust)
            base_table = tables[0]["name"]

        if not base_table:
            raise ValueError("Cannot determine base table from query and schema")

        # 3) Detect metrics
        #    Look for aggregate keywords next to a known column; else default to AVG on first numeric column hit; else *
        aggregates = {
            "avg": "AVG",
            "sum": "SUM",
            "count": "COUNT",
            "min": "MIN",
            "max": "MAX",
        }
        metric_exprs: List[str] = []

        # Find column mentions in query order
        mentioned_cols: List[Tuple[str, Dict[str, Any]]] = []  # (table_name, col_info)
        for tok in q_tokens:
            if tok in col_index:
                mentioned_cols.append(col_index[tok])

        # If explicit aggregate keyword present nearby, use it
        used_metric = False
        for agg_tok, agg in aggregates.items():
            if agg_tok in q_tokens:
                # choose the nearest mentioned column (prefer numeric if exists)
                target = None
                for tname, cinfo in mentioned_cols:
                    if self._is_numeric_type(str(cinfo.get("type"))):
                        target = (tname, cinfo)
                        break
                if not target and mentioned_cols:
                    target = mentioned_cols[0]
                if target:
                    metric_exprs.append(f"{agg}({target[1]['name']})")
                    used_metric = True
                    break

        if not used_metric:
            # choose first numeric column mentioned
            num_target = None
            for tname, cinfo in mentioned_cols:
                if self._is_numeric_type(str(cinfo.get("type"))):
                    num_target = (tname, cinfo)
                    break
            if num_target:
                metric_exprs.append(f"AVG({num_target[1]['name']})")
            else:
                # fallback
                metric_exprs.append("*")

        # 4) Detect simple filters of form column='value' or column=value
        #    We scan using regex for known column names to avoid guessing
        filters: List[str] = []
        query_str = query  # keep original for case/quotes
        for col_name, (tname, cinfo) in col_index.items():
            # Build safe regex for this column
            pattern = rf"\b{re.escape(col_name)}\b\s*=\s*'([^']+)'|\b{re.escape(col_name)}\b\s*=\s*([A-Za-z0-9_.-]+)"
            for m in re.finditer(pattern, query_str, flags=re.IGNORECASE):
                val = m.group(1) or m.group(2)
                if val is None:
                    continue
                # quote non-numeric values
                val_quoted = (
                    val if re.fullmatch(r"[-+]?[0-9]+(\.[0-9]+)?", val) else f"'{val}'"
                )
                filters.append(f"{col_name}={val_quoted}")

        # 5) Determine joins
        #    include any table that hosts a referenced column (from filters/metrics) and is not the base table,
        #    and is reachable from base_table in one hop via relationships.
        referenced_tables = set()
        # from filters
        for flt in filters:
            # flt format: name=...
            lhs = flt.split("=", 1)[0].strip().lower()
            if lhs in col_index:
                tname, _ = col_index[lhs]
                referenced_tables.add(tname)
        # from metrics (extract column names inside func)
        for m in metric_exprs:
            mcol = re.findall(r"\(([^)]+)\)", m)
            for mc in mcol:
                mc_l = mc.strip().lower()
                if mc_l in col_index:
                    tname, _ = col_index[mc_l]
                    referenced_tables.add(tname)

        # also include tables explicitly named in the query
        for name, toks in table_name_tokens.items():
            if any(tok in q_tokens for tok in toks):
                referenced_tables.add(name)

        joins: List[str] = []
        one_hop = neighbors.get(base_table, set())
        for tname in referenced_tables:
            if tname != base_table and tname in one_hop:
                joins.append(tname)

        # 6) Group/order: keep empty unless needed
        group_by: List[str] = []
        order_by: List[str] = []

        # 7) Limit: default 100 (allow override like "top 10" if you want later)
        limit = 100

        return {
            "base_table": base_table,
            "joins": sorted(set(joins)),
            "metrics": metric_exprs,
            "filters": filters,
            "group_by": group_by,
            "order_by": order_by,
            "limit": limit,
        }


schema_discovery = SchemaDiscovery()
