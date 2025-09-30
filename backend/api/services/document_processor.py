"""Service responsible for document ingestion and embedding preparation."""

from __future__ import annotations

import csv
import io
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

try:  # Optional readers
    import PyPDF2  # type: ignore
except Exception:  # pragma: no cover
    PyPDF2 = None

try:
    import docx  # python-docx  # type: ignore
except Exception:  # pragma: no cover
    docx = None

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None


@dataclass
class IngestionJob:
    id: str
    files: List[Path]
    status: str = "queued"  # queued | processing | completed | error
    processed: int = 0
    total: int = 0
    errors: List[str] = field(default_factory=list)
    index_ready: bool = False
    index_size: int = 0
    message: Optional[str] = None
    # In-memory artifacts
    tfidf: Optional[TfidfVectorizer] = None
    faiss_index: Optional[object] = None
    # Parallel arrays for chunks
    doc_ids: List[str] = field(default_factory=list)  # per-chunk doc title (filename)
    X_norm: Optional[np.ndarray] = None  # chunk vectors
    texts: List[str] = field(default_factory=list)  # chunk texts (snippets)
    # Map document ID (filename) to absolute file path for download
    file_map: Dict[str, str] = field(default_factory=dict)


class DocumentProcessor:
    """Coordinates multi-format document processing for retrieval with job tracking."""

    def __init__(self) -> None:
        self._jobs: Dict[str, IngestionJob] = {}
        self._lock = threading.Lock()

    # Public API
    def start_job(self, files: List[Path]) -> str:
        job_id = uuid.uuid4().hex
        job = IngestionJob(id=job_id, files=files, total=len(files))
        with self._lock:
            self._jobs[job_id] = job
        t = threading.Thread(target=self._worker, args=(job_id,), daemon=True)
        t.start()
        return job_id

    def get_status(self, job_id: str) -> Dict:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return {"status": "not_found", "job_id": job_id}
        progress = 0 if job.total == 0 else int((job.processed / job.total) * 100)
        return {
            "job_id": job.id,
            "status": job.status,
            "processed": job.processed,
            "total": job.total,
            "progress": progress,
            "errors": job.errors,
            "index_ready": job.index_ready,
            "index_size": job.index_size,
            "message": job.message,
        }

    # Worker
    def _worker(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return
        job.status = "processing"
        chunk_texts: List[str] = []
        chunk_doc_ids: List[str] = []
        try:
            for p in job.files:
                try:
                    text = self._extract_text(p)
                    chunks = self._dynamic_chunk(text, p.suffix.lower())
                    # record chunks with the filename as the document id/title
                    for ch in chunks:
                        chunk_texts.append(ch)
                        chunk_doc_ids.append(p.name)
                    job.file_map[p.name] = str(p)
                except Exception as exc:  # pragma: no cover
                    job.errors.append(f"{p.name}: {exc}")
                finally:
                    job.processed += 1
            # Build TF-IDF and FAISS (in-memory)
            if chunk_texts:
                tfidf = TfidfVectorizer(stop_words="english")
                X = tfidf.fit_transform(chunk_texts)  # sparse over chunks
                # normalize to unit vectors for cosine on inner product index
                X = X.astype(np.float32)
                # convert to dense float32 for faiss (may be memory heavy for many docs)
                X_dense = X.toarray().astype("float32")
                # L2 normalize
                norms = np.linalg.norm(X_dense, axis=1, keepdims=True) + 1e-12
                X_norm = X_dense / norms
                if faiss is not None:
                    index = faiss.IndexFlatIP(X_norm.shape[1])
                    index.add(X_norm)
                else:
                    index = None  # faiss not available; keep None
                job.tfidf = tfidf
                job.faiss_index = index
                job.doc_ids = chunk_doc_ids
                job.X_norm = X_norm
                job.texts = chunk_texts
                # Ready if either FAISS is available or we have normalized vectors
                job.index_ready = (index is not None) or (X_norm is not None)
                job.index_size = len(chunk_doc_ids)
            job.status = "completed"
            job.message = "ingestion_complete"
        except Exception as exc:  # pragma: no cover
            job.status = "error"
            job.message = f"ingestion_failed: {exc}"

    # Extraction helpers
    def _extract_text(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".txt":
            return path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".csv":
            return self._read_csv(path)
        if suffix == ".pdf" and PyPDF2 is not None:
            return self._read_pdf(path)
        if suffix in (".docx", ".doc") and docx is not None:
            return self._read_docx(path)
        # Fallback: binary read and decode best-effort
        try:
            with open(path, "rb") as f:
                raw = f.read()
            return raw.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _read_csv(self, path: Path) -> str:
        buf = io.StringIO()
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                buf.write(" ".join(row))
                buf.write("\n")
        return buf.getvalue()

    def _read_pdf(self, path: Path) -> str:
        text_parts: List[str] = []
        try:
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    txt = page.extract_text() or ""
                    text_parts.append(txt)
        except Exception:
            return ""
        return "\n".join(text_parts)

    # Download helpers
    def get_file_path(self, doc_id: str) -> Optional[Path]:
        with self._lock:
            jobs = list(self._jobs.values())
        if not jobs:
            return None
        for j in reversed(jobs):
            p = j.file_map.get(doc_id)
            if p and Path(p).exists():
                return Path(p)
        return None

    def _read_docx(self, path: Path) -> str:
        text_parts: List[str] = []
        try:
            d = docx.Document(str(path))
            for p in d.paragraphs:
                if p.text:
                    text_parts.append(p.text)
        except Exception:
            return ""
        return "\n".join(text_parts)

    # Chunking strategy: paragraph-based with size window
    def _dynamic_chunk(self, content: str, ext: str) -> List[str]:
        if not content:
            return []
        # Split by double newlines as paragraphs
        paras = [p.strip() for p in content.split("\n\n") if p.strip()]
        # Aim for chunks of ~800-1200 characters
        min_len, max_len = 600, 1200
        chunks: List[str] = []
        buf = []
        cur = 0
        for p in paras:
            if cur + len(p) + 2 <= max_len:
                buf.append(p)
                cur += len(p) + 2
            else:
                if cur >= min_len:
                    chunks.append("\n\n".join(buf))
                    buf = [p]
                    cur = len(p)
                else:
                    # if too small, still append but cap at max_len
                    buf.append(p)
                    cur += len(p) + 2
                    chunks.append("\n\n".join(buf))
                    buf = []
                    cur = 0
        if buf:
            chunks.append("\n\n".join(buf))
        # Fallback to slicing if content had no paragraphs
        if not chunks:
            text = content.strip()
            step = 1000
            for i in range(0, len(text), step):
                chunks.append(text[i : i + step])
        return chunks

    # Search API
    def search(self, query: str, top_k: int = 5) -> Dict:
        """Search the most recent ingested corpus using TF-IDF/FAISS.

        Returns a dict with keys: results (list of {id, title, score, snippet}), total_docs
        """
        with self._lock:
            # Pick the latest job with a built index
            jobs = list(self._jobs.values())
        if not jobs:
            return {"results": [], "total_docs": 0}
        # iterate reversed to get the most recent created
        job = None
        for j in reversed(jobs):
            if j.tfidf is not None and (
                j.faiss_index is not None or j.X_norm is not None
            ):
                job = j
                break
        if job is None:
            return {"results": [], "total_docs": 0}

        if not query or not isinstance(query, str):
            return {"results": [], "total_docs": len(set(job.doc_ids))}

        tfidf = job.tfidf
        assert tfidf is not None
        q_vec = tfidf.transform([query]).toarray().astype("float32")
        # L2 normalize
        q_norm = q_vec / (np.linalg.norm(q_vec, axis=1, keepdims=True) + 1e-12)

        scores: np.ndarray
        indices: np.ndarray
        if job.faiss_index is not None:
            # type: ignore[attr-defined]
            D, I = job.faiss_index.search(q_norm, min(top_k, job.index_size))  # type: ignore[arg-type]
            scores = D.flatten()
            indices = I.flatten()
        elif job.X_norm is not None:
            # cosine via dot product with normalized matrix
            scores = (job.X_norm @ q_norm.T).flatten()
            # get top_k indices
            top_k = min(top_k, scores.shape[0])
            indices = np.argsort(-scores)[:top_k]
            scores = scores[indices]
        else:
            return {"results": [], "total_docs": len(set(job.doc_ids))}

        results: List[Dict] = []
        for rank, (idx, score) in enumerate(zip(indices.tolist(), scores.tolist())):
            if idx is None or idx < 0 or idx >= len(job.doc_ids):
                continue
            doc_id = job.doc_ids[idx]
            title = job.doc_ids[idx]
            text = job.texts[idx] if idx < len(job.texts) else ""
            snippet = (text[:240] + ("..." if len(text) > 240 else "")) if text else ""
            results.append(
                {
                    "id": doc_id,
                    "title": title,
                    "score": float(score),
                    "snippet": snippet,
                    "rank": rank + 1,
                }
            )

        return {"results": results, "total_docs": len(set(job.doc_ids))}
