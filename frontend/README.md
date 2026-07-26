# ProtDAP frontend

React + Vite + TypeScript + Tailwind panel for the ProtDAP backend
(`../app`). Chat with the ReAct agent in the center panel; every UniProt
hit and proposed candidate from the whole conversation accumulates in the
side panels, with inline highlighting of proposed mutations and an
embedded Mol* 3D viewer for folded structures.

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

Opens on `http://localhost:5173`. In dev, Vite proxies `/chat`,
`/structures/*`, and `/liveness` to `http://127.0.0.1:8000` (see
`vite.config.ts`), so the app can use relative fetch paths and the
session cookie is treated as same-origin. Override the backend target with
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
  state/          # conversationStore: turns + accumulated proteins/candidates,
                  # persisted to localStorage
  components/
    chat/         # Transcript, message bubbles, collapsible tool-trace details
    proteins/     # Retrieved-protein cards (side panel)
    candidates/   # Candidate cards: sequence view with highlighted
                  # mutations, modifications table, export buttons
    structure/    # Mol* 3D structure viewer
    layout/       # Overall page shell
```

Notes:

- The backend only returns the latest turn's data (full context lives
  server-side via the session cookie), so the frontend keeps its own
  transcript and accumulated `retrieved_proteins`/`candidates` lists
  (deduped by `accession`/`sequence`) in `state/conversationStore.tsx`,
  persisted to `localStorage` so a page refresh doesn't lose them.
- All interaction happens through the chat input - protein/candidate cards
  are read-only (no quick-action buttons that auto-send messages) by
  design for this version.
