# NLP Query Engine — Local Setup (uv + npm)

This repo contains a FastAPI backend (Python) and a React + Vite frontend (TypeScript) that together power a natural language query engine over relational data and uploaded documents.

This README shows how to get everything running locally using:
- uv (Python packaging/runtime manager)
- npm (Node.js package manager)

No Docker required.

## Prerequisites

- Python 3.11+ installed
- Node.js 18+ and npm 9+
- uv installed (https://docs.astral.sh/uv/):
	- Windows: `pip install uv`
	- macOS/Linux (Homebrew): `brew install astral-sh/uv/uv`

If you prefer another way to install uv, follow their docs.

## 1) Backend (FastAPI) — using uv

From the repository root:

```bash
cd backend
# Create & activate the virtual environment and install deps
uv sync

# Run the API server
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Notes
- The backend exposes endpoints under `http://localhost:8000/api/*`.
- Make sure the terminal stays open while the server runs.
- If you change Python files, `--reload` will auto-restart.

Optional
- If you need to add a new Python package:
```bash
uv add <package-name>
```
This updates `pyproject.toml` and `uv.lock` deterministically.

## 2) Frontend (Vite + React) — using npm

Open a new terminal (keep the backend running) and from the repo root:

```bash
cd frontend
npm install
npm run dev
```

By default the dev server runs on `http://localhost:5173` and proxies API calls to `http://localhost:8000` if configured. If your backend runs elsewhere, set `VITE_API_BASE_URL` in `frontend/.env`:

```ini
# frontend/.env
VITE_API_BASE_URL=http://localhost:8000
```

## 3) Connect a database and upload documents

- Click the Database icon to open the connection modal and paste a valid SQLAlchemy connection URL.
	- Postgres examples:
		- `postgresql://user:pass@localhost:5432/mydb`
		- `postgres://user:pass@localhost/mydb`
	- SQLite example:
		- `sqlite:///C:/absolute/path/to/test_cli.db`
- The backend will discover schema (tables, columns, relationships). For Postgres it includes all non-system schemas (public + user-defined).
- Use the Documents icon to upload PDFs, DOCX, TXT, or CSV files. The UI shows per-file progress and an overall circular summary.

## 4) Ask questions

Type a question in the composer:
- If the classifier is confident for SQL, it builds and executes a safe SELECT with joins and pagination.
- If it’s confident for documents, it searches your uploaded chunks (TF‑IDF / FAISS when available).
- If both are confident, you get a hybrid result.
- If neither modality crosses the threshold, you’ll see an informative message (low confidence) and no execution.

The UI shows:
- Query summary with timing and cache status (e.g., “Query took 1.2s (cache hit)”).
- A horizontal metrics strip (latency, cache, SQL/Docs time, totals, hit rate, avg time).
- Results (table rows and/or document snippets) with download links for originals.
- Schema visualizer and modals to explore tables/columns.

## Troubleshooting

- SQLAlchemy imports unresolved in editor: that’s just your editor not using the uv venv. The server still runs via `uv run`. If you want editor intellisense, activate `backend/.venv` in your IDE.
- Slow first query: the first run warms caches and builds indices. Subsequent runs should be faster; cache hit/miss is reported in metrics.
- Postgres schemas: we include all non-system schemas. If you want to exclude some (e.g., staging/archive), we can add a filter.
- Frontend can’t reach backend: ensure `VITE_API_BASE_URL` matches the backend host/port and that the backend terminal is running.

## Development tips

- Add Python deps: `uv add package` (or remove with `uv remove package`).
- Format/lint: use your editor or preferred tools; uv keeps a clean, reproducible environment.
- For UI tweaks, edit `frontend/src` and the Vite dev server will hot‑reload.

## Assignment reference

For deeper context on goals, constraints, and evaluation, see the original assignment PDF included in this repo: `AI Engineering Assignment_ NLP Query Engine (1).pdf`. It serves as the source of truth for expected behaviors and deliverables.

---

Happy hacking! If you’d like, I can add scripts to run both servers in one command (e.g., npm scripts that spawn the backend via `uv run`).
