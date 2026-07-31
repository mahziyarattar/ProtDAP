# ProtDAP - Protein Diversification Agent Platform

ProtDAP is a backend service built around a **ReAct agent** that helps
computational/wet-lab biologists **search** real, existing proteins and
**diversify** them: propose sequence variants of a known parent protein
(e.g. "more stable", "improve X"), fold the proposals to get a structure
confidence estimate, and return everything with clear, code-enforced
**provenance labels** - so a retrieved natural sequence is never confused
with a computationally-proposed one.

This project is being built as a master's thesis prototype in biophysics.
It intentionally favors free/open backends (UniProt REST for protein
knowledge) plus a real hosted model backend (BioLM, via a genuine MCP
client) over rebuilding a private protein database from scratch.

## What it actually does

1. You send a message to `POST /chat` (e.g. *"Find a small human protein
   and propose 3 more stable variants"*).
2. A LangGraph ReAct agent (Gemini 2.5 Flash via OpenRouter) decides which
   tools to call: `search_uniprot`, `map_to_uniprot`, `get_uniprot_entry`,
   `search_protrek` (optional), `propose_variants`, `fold_sequence`,
   `score_variant`.
3. Every tool call and its raw result is recorded in a tool-call trace.
4. A **deterministic Python assembler** (not the LLM) walks that trace and
   builds the structured `retrieved_proteins` and `candidates` lists, so the
   schema (provenance, parent, % identity, pLDDT) is always correct
   regardless of what the model's prose says.
5. You get back a natural-language `reply` plus the structured, labeled
   data - and can fetch any predicted structure's PDB text from
   `GET /structures/{structure_id}` for 3D visualization.
6. Separately from the chat loop, `POST /fold` lets the frontend (or any
   client) fold an arbitrary sequence on demand - used so a retrieved
   search hit can be viewed in 3D without asking the agent to fold it.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design, the candidate
schema, and the reliability rationale.

## What this is *not*

- Not a replacement for validated protein design tools like ProteinMPNN or
  RFdiffusion - v1 sequence generation is LLM-based and always labeled
  `origin: llm_proposed`, never presented as a validated design. See
  "Future work" in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Not a private re-embedded protein database - protein knowledge/search
  comes directly from the free, public UniProt REST API.
- pLDDT (from BioLM ESMFold) is reported as a structure-confidence
  **filter/signal**, never as proof that a sequence is functional.

## Prerequisites

- **Python 3.11+**
- **Node.js + npx** - required to spawn the real BioLM MCP server
  (`@biolm/biolm-mcp`) as a subprocess over stdio. Check with:
  ```bash
  node --version && npx --version
  ```
- An **OpenRouter** API key (for the ReAct agent's LLM calls).
- A **BioLM** API token (for `fold_sequence` / `score_variant`). UniProt
  needs no key at all.

## Setup

```bash
cd "ProtDAP"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# then edit .env and fill in OPENROUTER_API_KEY and BIOLMAI_TOKEN
```

### Environment variables (`.env`)

| Variable | Purpose | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | Required. Auth for the ReAct agent's LLM calls. | - |
| `OPENROUTER_MODEL` | Model used for both the agent and `propose_variants`. | `google/gemini-2.5-flash` |
| `OPENROUTER_BASE_URL` | OpenRouter's OpenAI-compatible endpoint. | `https://openrouter.ai/api/v1` |
| `BIOLMAI_TOKEN` | Required. Auth passed to the BioLM MCP subprocess. | - |
| `UNIPROT_BASE_URL` | UniProt REST API base (free, keyless). | `https://rest.uniprot.org` |
| `DEFAULT_RESULT_SIZE` | Default number of search hits when the user doesn't specify a count. | `5` |
| `SESSION_TTL_SECONDS` | In-memory session lifetime. | `3600` |
| `FRONTEND_ORIGIN` | Allowed CORS origin for the React panel (credentials enabled). | `http://localhost:5173` |
| `EVAL_LIVE` | `0` = smoke eval uses recorded UniProt/BioLM fixtures; `1` = hits the real APIs. | `0` |

## Running the server

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

On startup, ProtDAP runs a one-off BioLM MCP connectivity check (spawns
`npx -y @biolm/biolm-mcp`, completes the handshake, closes it again) so a
bad token or missing Node/npx shows up in the logs immediately; if it's
slow or fails, it logs a warning and keeps serving requests regardless.
Every actual `fold_sequence`/`score_variant` call then opens its own fresh
connection (see `app/tools/biolm_mcp.py` for why a single shared connection
isn't safe across the agent's concurrent tool calls) - the first real fold
in a session takes a few extra seconds for `npx` to start the server.

Check it's alive:

```bash
curl http://localhost:8000/liveness
```

For manual API checks (sample request bodies, session cookies, response
field shapes, `/fold`, and `/structures/{id}`), see [docs/TESTING.md](docs/TESTING.md).

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173`. In dev, Vite proxies `/chat`, `/fold`,
`/structures/*`, and `/liveness` to the backend so the session cookie is
same-origin. The right panel is tabbed (Proteins / Candidates / Structures);
the Structures tab overlays up to 5 selected molecules in one Mol* viewer
(fold-on-select via `POST /fold` for unfolder proteins). Cards link via
"View in Structures". Details in [frontend/README.md](frontend/README.md).

## Testing

Automated tests are below. Manual curl walkthroughs live in
[docs/TESTING.md](docs/TESTING.md).

Fast, fully offline unit tests for the UniProt REST tool (fixtures + a
mocked 429-retry check, no network, no API keys needed):

```bash
pytest app/tools/test_uniprot.py -v
```

The full test suite:

```bash
pytest
```

### Smoke eval (integration-level, needs a real OpenRouter key)

```bash
python -m app.eval.smoke_eval
```

This runs 5 fixed end-to-end cases against the real ReAct agent loop. By
default (`EVAL_LIVE=0`) the UniProt/BioLM *tool* calls are replaced with
recorded fixtures (so no BioLM token or UniProt network access is required
for that part), but the LLM call itself is always real, since that's the
actual thing being smoke-tested. Set `EVAL_LIVE=1` to also hit the real
UniProt and BioLM APIs.

## Project layout

```
app/
  main.py              FastAPI app: POST /chat, POST /fold, GET /structures/{id}, GET /liveness
  config.py            Environment-based configuration + validation
  models.py            Pydantic schemas (ChatRequest/Response, FoldRequest, ProteinHit, Candidate, ...)
  session.py           In-memory, cookie-backed session store
  structure_cache.py   In-memory {structure_id: pdb_text} cache
  agent/
    graph.py           Builds/runs the LangGraph ReAct agent + tool trace
    prompts.py         System prompt (search/diversify/fold rules)
    assembler.py       Deterministic trace -> retrieved_proteins/candidates
  tools/
    uniprot.py         UniProt REST client (search + get entry, 429 handling)
    uniprot_idmapping.py  UniProt ID Mapping client (map_to_uniprot)
    test_uniprot.py    Offline unit tests for the above
    biolm_mcp.py        Real BioLM MCP client (stdio) - fold_sequence, score_variant
    generation.py       propose_variants (LLM-based sequence proposals)
    identity.py         Pairwise sequence identity (Biopython)
  eval/
    smoke_eval.py       5-case integration smoke eval
    fixtures/           Recorded UniProt/BioLM responses used by tests + smoke eval
docs/                  Architecture, tools, ID mapping, ProTrek, manual API testing
frontend/              React + Vite + TypeScript + Tailwind panel (chat + protein/candidate
                       panels + Mol* 3D viewer; see frontend/README.md)
```

## Status

Backend prototype with a React frontend panel in `frontend/` (chat,
tabbed Proteins/Candidates/Structures panels, Mol* overlay viewer with
on-demand fold via `POST /fold`). See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and "Future work"
(ProteinMPNN as the planned next generation method). More detail:
[docs/TOOLS.md](docs/TOOLS.md), [docs/IDMAPPING.md](docs/IDMAPPING.md),
[docs/PROTREK.md](docs/PROTREK.md).
