# ProtDAP frontend

React + Vite + TypeScript + Tailwind panel for the ProtDAP backend
(`../app`). Chat with the ReAct agent in the center panel; every UniProt
hit and proposed candidate from the whole conversation accumulates in the
right-hand tabs (Proteins / Candidates / Structures), with inline
highlighting of proposed mutations and a single Mol* viewer that can
overlay up to 5 selected structures. The Proteins tab lists every
retrieved hit; when the agent calls `recommend_proteins`, recommended
accessions sort to the top with a badge and others are dimmed.

## Prerequisites

- Node.js and npm.
- The FastAPI backend running and reachable (see the repo root `README.md`
  for backend setup: `.env` with `OPENROUTER_API_KEY`/`BIOLMAI_TOKEN`, then
  `uvicorn app.main:app --reload`, default `http://127.0.0.1:8000`).

## Running

```bash
npm install
npm run dev
```

Opens on `http://localhost:5173`. In dev, Vite proxies `/chat` (and
`/chat/stream`), `/fold`, `/structures/*`, and `/liveness` to
`http://127.0.0.1:8000` (see `vite.config.ts`), so the app can use relative
fetch paths and the session cookie is treated as same-origin. The proxy
disables buffering for `text/event-stream` so SSE status/token events
arrive promptly. Override the backend target with
`VITE_BACKEND_ORIGIN=http://127.0.0.1:8001 npm run dev` if the backend runs
on a different port.

If you instead call the backend directly from a built/deployed frontend
(no proxy), the backend's `CORSMiddleware` (`app/main.py`) allows the
origin configured via `FRONTEND_ORIGIN` (backend env var, default
`http://localhost:5173`) with credentials enabled.

## Build

```bash
npm run build
```

`predev`/`prebuild` automatically copy Mol*'s prebuilt viewer bundle from
`node_modules/molstar/build/viewer` into `public/molstar-viewer` (see
`scripts/copy-molstar-assets.mjs`) - it's a global-script bundle, not an ES
module, so it's loaded via a plain `<script>`/`<link>` tag at runtime
(`src/components/structure/StructureViewer.tsx`) rather than imported.

## Project structure

```
src/
  api/            # Types mirroring app/models.py, and the fetch client
                  # (POST /chat kept for non-UI; UI uses POST /chat/stream SSE)
  state/          # conversationStore (chat + accumulated lists, localStorage)
                  # + structuresStore (overlay selection, on-demand folds; not persisted)
  components/
    chat/         # Transcript, message bubbles, status line, collapsible tool-trace
    proteins/     # Retrieved-protein cards
    candidates/   # Candidate cards: sequence view with highlighted
                  # mutations, modifications table, export buttons
    structure/    # StructuresPanel (multi-select overlay) + Mol* StructureViewer
    layout/       # Overall page shell with Proteins | Candidates | Structures tabs
```

Notes:

- The chat UI always calls `POST /chat/stream` (SSE). While the agent runs,
  a status line appears above the partial assistant bubble (e.g. "Searching
  UniProt…"); reply tokens append into that bubble. `retrieved_proteins` /
  `candidates` / highlights arrive only on the final `done` event (same
  shape as `ChatResponse`). Non-streaming `POST /chat` remains available
  for curl and other API clients.
- The backend only returns the latest turn's data (full context lives
  server-side via the session cookie), so the frontend keeps its own
  transcript and accumulated `retrieved_proteins`/`candidates` lists
  (deduped by `accession`/`sequence`) in `state/conversationStore.tsx`,
  persisted to `localStorage` so a page refresh doesn't lose them.
- 3D viewing lives only in the **Structures** tab: checkboxes select up to
  5 items (retrieved proteins and/or candidates); all checked items load
  into one Mol* scene as an as-is overlay (no superposition). Checking an
  unfolder protein triggers `POST /fold` on demand. Overlay selection is
  session-UI state only (not written to `localStorage`).
- **Expand** (header button, enabled when ≥1 item is selected) opens a
  fullscreen Structures mode: chat hidden; left column shows full
  Protein/Candidate cards for the selection plus the checkbox catalog;
  right column is a large Mol* overlay. **Collapse** or **Esc** exits.
  Mol*'s own viewport expand control is disabled to avoid a conflicting
  fullscreen.
- Protein/candidate cards stay mostly read-only (no chat quick-actions);
  each has a **"View in Structures"** shortcut that opens the Structures
  tab and adds that item to the overlay set (if under the cap).