"""Service orchestrating query classification, execution, and optimization."""

from typing import Any, Dict, List, Tuple
from time import perf_counter
import re

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .schema_discovery import schema_discovery
from ..routes.ingestion import processor  # module-level singleton for docs


class QueryCache:
    """Placeholder cache structure for storing query results and metadata."""

    def __init__(self) -> None:
        """Initialize cache state for query responses."""
        pass


class QueryEngine:
    """Main entry point for processing user queries across data sources."""

    def __init__(self, connection_string: str):
        """Auto-discover schema on initialization and prepare cache structures."""
        self.connection_string = connection_string
        self.engine: Engine = create_engine(connection_string, pool_pre_ping=True)
        self.schema = schema_discovery.analyze_database(connection_string)
        # Precompute relationship index for join inference
        self._tables = self.schema.get("tables", [])
        self._rels = self.schema.get("relationships", [])
        self.cache = QueryCache()

    def process_query(
        self, user_query: str, page: int | None = None, page_size: int | None = None
    ) -> Dict[str, Any]:
        """
        Process natural language query with a rule-based classifier:
        - Classify into sql, docs, or hybrid with a confidence score in [0,1]
        - Only execute when confidence > 0.5; otherwise return a low-confidence response
        - For sql: map NL to AST, build SQL, and safely execute read-only queries
        - For docs: run TF-IDF/FAISS search over ingested documents
        - For hybrid: run both and combine
        """
        # 0) Classify the query
        qtype, confidence, reasons, scores = self._classify(user_query)
        base_response: Dict[str, Any] = {
            "query": user_query,
            "query_type": qtype,
            "confidence": round(confidence, 3),
            "classification_reasons": reasons,
            "classification_scores": {k: round(v, 3) for k, v in scores.items()},
            "performance_metrics": {},
            "sources": [],
        }
        # NOTE: For now we will run both SQL and document search regardless of confidence,
        # and decide later based on per-type confidence thresholds. This ensures the UI
        # receives both result types while we keep computing confidence scores.
        # SQL part
        ast = schema_discovery.map_natural_language_to_schema(user_query, self.schema)
        sql = self._build_sql(ast, page=page, page_size=page_size)
        rows: List[Dict[str, Any]] = []
        executed_sql = False
        sql_ms: float | None = None
        sql_skip: str | None = None
        if self._can_execute(sql):
            try:
                t0 = perf_counter()
                with self.engine.connect() as conn:
                    result = conn.exec_driver_sql(sql)
                    rows = [dict(row._mapping) for row in result]
                sql_ms = (perf_counter() - t0) * 1000.0
                executed_sql = True
            except Exception as exc:
                sql_skip = f"execution_error: {exc}"
        else:
            sql_skip = "unsafe_or_incomplete_sql"

        # Docs part
        t0 = perf_counter()
        search = processor.search(user_query, top_k=5)
        doc_ms = (perf_counter() - t0) * 1000.0

        resp = {
            **base_response,
            "query_type": "hybrid",
            "ast": ast,
            "sql": sql,
            "executed": executed_sql or bool(search.get("results")),
            "rows": rows,
            "documents": search.get("results", []),
            "sources": [
                s
                for s in [
                    "sql" if executed_sql else None,
                    "documents" if search.get("results") else None,
                ]
                if s
            ],
        }
        if page_size:
            resp.setdefault("pagination", {})["page_size"] = page_size
        if page:
            resp.setdefault("pagination", {})["page"] = page
        if sql_ms is not None:
            resp["performance_metrics"]["exec_ms"] = sql_ms
        resp["performance_metrics"]["doc_search_ms"] = doc_ms
        if sql_skip:
            resp["execution_skipped_reason_sql"] = sql_skip
        return resp

    def _quote_ident(self, name: str) -> str:
        # Basic identifier quoting; adapt per dialect if needed
        if name is None:
            return name
        # If name already schema-qualified, quote each part
        parts = name.split(".")
        return ".".join(f'"{p}"' for p in parts)

    def _build_sql(
        self,
        ast: Dict[str, Any],
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> str:
        base = ast.get("base_table")
        joins = ast.get("joins", [])
        metrics = ast.get("metrics", [])
        filters = ast.get("filters", [])
        group_by = ast.get("group_by", [])
        order_by = ast.get("order_by", [])
        # Pagination overrides ast limit when provided
        if page_size is not None and page_size > 0:
            limit = int(page_size)
            offset = int(max(0, ((page or 1) - 1) * page_size))
        else:
            limit = int(ast.get("limit", 100))
            offset = 0

        # SELECT list
        select_list = ", ".join(metrics) if metrics else "*"

        # FROM
        from_sql = f"FROM {self._quote_ident(base)}"

        # JOINs (infer ON clause using relationships graph)
        join_sql_parts = []
        for jt in joins:
            on_sql, status = self._infer_join_on(base, jt)
            if status == "ok" and on_sql:
                join_sql_parts.append(f"JOIN {self._quote_ident(jt)} ON {on_sql}")
            elif status == "ambiguous":
                join_sql_parts.append(
                    f"JOIN {self._quote_ident(jt)} ON /* ambiguous_join */ 1=0"
                )
            else:
                join_sql_parts.append(
                    f"JOIN {self._quote_ident(jt)} ON /* no_relation */ 1=0"
                )
        join_sql = "\n".join(join_sql_parts)

        # WHERE
        where_sql = ""
        if filters:
            where_sql = "WHERE " + " AND ".join(filters)

        # GROUP BY / ORDER BY
        group_sql = f"GROUP BY {', '.join(group_by)}" if group_by else ""
        order_sql = f"ORDER BY {', '.join(order_by)}" if order_by else ""

        # LIMIT / OFFSET
        limit_sql = f"LIMIT {int(limit)}"
        if offset:
            limit_sql += f" OFFSET {offset}"

        sql_parts = [
            f"SELECT {select_list}",
            from_sql,
            join_sql,
            where_sql,
            group_sql,
            order_sql,
            limit_sql,
        ]
        sql = "\n".join([p for p in sql_parts if p])
        return sql

    def _resolve_table(self, name: str) -> Dict[str, Any] | None:
        if not name:
            return None
        target = name.lower().split(".")[-1]
        for t in self._tables:
            # prefer base_name if present
            for key in ("base_name", "name", "fq_name"):
                v = t.get(key)
                if isinstance(v, str) and v:
                    if v.lower().split(".")[-1] == target or v.lower() == name.lower():
                        return t
        return None

    def _infer_join_on(
        self, base_table: str, join_table: str
    ) -> Tuple[str | None, str]:
        """Return (on_sql, status) where status in {'ok','ambiguous','none'}."""
        bt = self._resolve_table(base_table)
        jt = self._resolve_table(join_table)
        if not bt or not jt:
            return None, "none"
        bt_name = bt.get("name") or bt.get("fq_name") or bt.get("base_name")
        jt_name = jt.get("name") or jt.get("fq_name") or jt.get("base_name")
        if not isinstance(bt_name, str) or not isinstance(jt_name, str):
            return None, "none"
        bt_name_l = bt_name.lower()
        jt_name_l = jt_name.lower()
        candidates: List[Tuple[str, str]] = []
        for r in self._rels:
            t = str(r.get("table", "")).lower()
            rt = str(r.get("referred_table", "")).lower()
            if (
                t.split(".")[-1] == bt_name_l.split(".")[-1]
                and rt.split(".")[-1] == jt_name_l.split(".")[-1]
            ):
                # table.column = referred_table.referred_column
                lc = str(r.get("column"))
                rc = str(r.get("referred_column"))
                candidates.append(
                    (
                        f"{self._quote_ident(bt_name)}.{self._quote_ident(lc)} = {self._quote_ident(jt_name)}.{self._quote_ident(rc)}",
                        "forward",
                    )
                )
            elif (
                t.split(".")[-1] == jt_name_l.split(".")[-1]
                and rt.split(".")[-1] == bt_name_l.split(".")[-1]
            ):
                lc = str(r.get("column"))
                rc = str(r.get("referred_column"))
                candidates.append(
                    (
                        f"{self._quote_ident(jt_name)}.{self._quote_ident(lc)} = {self._quote_ident(bt_name)}.{self._quote_ident(rc)}",
                        "reverse",
                    )
                )

        if not candidates:
            return None, "none"
        # Deduplicate and evaluate ambiguity
        unique = list({c[0] for c in candidates})
        if len(unique) == 1:
            return unique[0], "ok"
        return None, "ambiguous"

    def _can_execute(self, sql: str) -> bool:
        """Guardrail: execute only simple SELECTs and avoid placeholder JOINs for now."""
        if not sql:
            return False
        if "/* TODO: infer join condition */" in sql:
            return False
        if "/* ambiguous_join */" in sql or "/* no_relation */" in sql:
            return False
        if ";" in sql:
            return False
        # Must start with SELECT (allow leading whitespace)
        return bool(re.match(r"^\s*SELECT\b", sql, flags=re.IGNORECASE))

    # --- Classification ---
    def _classify(self, q: str) -> Tuple[str, float, List[str], Dict[str, float]]:
        """Simple rule-based classifier returning (type, confidence, reasons, scores).

        Heuristics (scored 0..1 then normalized):
        - SQL intent signals: presence of SQL verbs, schema/table words, aggregations, group/order/where tokens
        - Docs intent signals: words like "resume", "document", "policy", "PDF", "notes", "explain", "summarize"
        - Hybrid signals: keywords suggesting both structured and unstructured or a mix (e.g., skills AND salary)
        """
        text = (q or "").strip().lower()
        reasons: List[str] = []
        if not text:
            return ("sql", 0.0, ["empty_query"])

        # Signals
        sql_tokens = [
            "select",
            "from",
            "where",
            "join",
            "group by",
            "order by",
            "limit",
            "count",
            "avg",
            "sum",
            "min",
            "max",
            "having",
        ]
        sql_nl_hints = [
            # intent words
            "how many",
            "list",
            "show",
            "top",
            "highest",
            "lowest",
            "average",
            "by department",
            # quantifiers / aggregations
            "number of",
            "count of",
            "count",
            "total",
            # domain-y hints (generic employee DBs)
            "employees",
            "staff",
            "departments",
            "manager",
            "salary",
            "compensation",
            "pay",
        ]
        doc_tokens = [
            "document",
            "documents",
            "resume",
            "resumes",
            "pdf",
            "docx",
            "policy",
            "contract",
            "review",
            "notes",
            "report",
            "emails",
            "attachments",
            "snippet",
            "text",
        ]
        hybrid_hints = [
            "skills",
            "resume mentions",
            "documents mentioning",
            "from database and documents",
            "both",
        ]

        # Quick tokens for matching
        q_tokens_simple = re.findall(r"[a-z0-9_]+", text)

        # Scores
        s_sql = 0.0
        s_doc = 0.0
        s_hybrid = 0.0

        # Direct SQL tokens
        for t in sql_tokens:
            if t in text:
                s_sql += 0.08
        # Natural language hints for SQL over structured data
        for t in sql_nl_hints:
            if t in text:
                s_sql += 0.05

        # Document tokens
        for t in doc_tokens:
            if t in text:
                s_doc += 0.1

        # Document title boosting: if query matches any ingested doc title tokens, favor docs path
        try:
            # Access latest job titles from the processor singleton
            titles_tokens: set[str] = set()
            with processor._lock:
                jobs = list(processor._jobs.values())  # type: ignore[attr-defined]
            for j in reversed(jobs):
                doc_ids = getattr(j, "doc_ids", []) or []
                if doc_ids:
                    for name in doc_ids:
                        # use stem-ish tokens (drop extension); split alphanum
                        name_l = str(name).lower()
                        # strip extension if present
                        if "." in name_l:
                            name_l = name_l.rsplit(".", 1)[0]
                        for tok in re.findall(r"[a-z0-9_]+", name_l):
                            if tok:
                                titles_tokens.add(tok)
                    break
            if titles_tokens and any(tok in titles_tokens for tok in q_tokens_simple):
                s_doc += 0.3
                # capture one example token for reasons
                match_tok = next((tok for tok in q_tokens_simple if tok in titles_tokens), None)
                if match_tok:
                    reasons.append(f"doc_title_match={match_tok}")
        except Exception:
            pass

        # Hybrid cues: skills + salary/pay, or explicit hybrid words
        salary_words = [
            "salary",
            "compensation",
            "pay",
            "highest paid",
            "over",
            "under",
        ]
        skill_words = [
            "skill",
            "skills",
            "python",
            "java",
            "sql",
            "engineer",
            "developer",
        ]
        if any(w in text for w in hybrid_hints):
            s_hybrid += 0.3
        if any(w in text for w in salary_words) and any(w in text for w in skill_words):
            s_hybrid += 0.3
        # If both sql and docs are signaled reasonably, bump hybrid
        if s_sql >= 0.3 and s_doc >= 0.2:
            s_hybrid += 0.3

        # If explicit SELECT-like syntax present, that strongly favors SQL
        if re.search(r"\bselect\b.*\bfrom\b", text):
            s_sql += 0.5
            reasons.append("explicit_select_syntax")

        # Schema-aware boosting: exact and fuzzy matches for table/column names
        try:
            tokens = re.findall(r"[a-z0-9_]+", text)
            tokens = [t for t in tokens if len(t) >= 3]
            table_names: List[str] = []
            column_names: List[str] = []
            for tinfo in self.schema.get("tables", []):
                # try a few variants safely
                for key in ("base_name", "name", "fq_name"):
                    val = tinfo.get(key)
                    if isinstance(val, str) and val:
                        # use only the last part for fq_name
                        tn = val.split(".")[-1].lower()
                        table_names.append(tn)
                for c in tinfo.get("columns", []):
                    cname = c.get("name") if isinstance(c, dict) else None
                    if isinstance(cname, str) and cname:
                        column_names.append(cname.lower())
            # Exact matches
            for tok in tokens:
                if tok in table_names or tok in column_names:
                    s_sql += 0.08
                    reasons.append(f"schema_token={tok}")

            # Fuzzy (edit distance 1) against table names to catch minor typos like 'threds' vs 'threads'
            def _is_one_edit(a: str, b: str) -> bool:
                # Damerau-Levenshtein distance simplified to allow at most 1 edit (insert/delete/substitute)
                if a == b:
                    return True
                la, lb = len(a), len(b)
                if abs(la - lb) > 1:
                    return False
                # Ensure a is shorter or equal
                if la > lb:
                    a, b = b, a
                    la, lb = lb, la
                i = j = edits = 0
                while i < la and j < lb:
                    if a[i] == b[j]:
                        i += 1
                        j += 1
                    else:
                        edits += 1
                        if edits > 1:
                            return False
                        if la == lb:
                            i += 1
                            j += 1  # substitution
                        else:
                            j += 1  # insertion in b or deletion in a
                # account for trailing char
                if j < lb or i < la:
                    edits += 1
                return edits <= 1

            for tok in tokens:
                if any(_is_one_edit(tok, tn) for tn in table_names):
                    s_sql += 0.1
                    reasons.append(f"fuzzy_table={tok}")
                    break
        except Exception:
            # schema or parsing issues should not break classification
            pass

        # Normalize and choose
        scores = {"sql": s_sql, "docs": s_doc, "hybrid": s_hybrid}
        # small smoothing
        for k in scores:
            scores[k] = max(0.0, min(1.0, scores[k]))
        # pick best
        qtype = max(scores, key=scores.get)
        best = scores[qtype]
        # confidence is best minus next best margin to reflect uncertainty
        ordered = sorted(scores.values(), reverse=True)
        margin = (ordered[0] - ordered[1]) if len(ordered) > 1 else ordered[0]
        confidence = max(0.0, min(1.0, best))
        # Adjust by margin (scale 0.0-1.0)
        confidence = float(
            min(1.0, confidence * (0.6 + 0.4 * (margin if margin > 0 else 0)))
        )

        # Reasons
        reasons.extend(
            [f"score_{k}={scores[k]:.2f}" for k in ["sql", "docs", "hybrid"]]
        )
        reasons.append(f"margin={margin:.2f}")

        return qtype, confidence, reasons, scores

    def optimize_sql_query(self, sql: str) -> str:
        """
        Optimize generated SQL:
        - Use indexes when available
        - Limit result sets appropriately
        - Add pagination for large results
        """
        raise NotImplementedError("Implementation pending")
