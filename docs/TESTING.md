# Manual API testing

Curl-based checks against a running ProtDAP server. For automated tests
(`pytest`, smoke eval), see [README.md](../README.md#testing).

## Prerequisites

1. `.env` filled in (`OPENROUTER_API_KEY`, `BIOLMAI_TOKEN`).
2. Server running (from Run and Debug, or `uvicorn app.main:app --reload`).
3. Base URL: `http://localhost:8000`.

`/chat` can take tens of seconds (LLM + UniProt + BioLM MCP spawn/fold).

---

## `GET /liveness`

```bash
curl -s http://localhost:8000/liveness
```

**Expected shape:**

```json
{
  "status": "ok",
  "biolm_mcp_last_check_ok": true
}
```

`biolm_mcp_last_check_ok` may be `false` or `null` if the startup BioLM
check failed or has not succeeded yet; the server still serves requests.

---

## `POST /chat`

### Request body

| Field | Type | Required | Description |
|---|---|---|---|
| `message` | string | yes | Natural-language user turn. Mention a UniProt accession in the text if you already know one (e.g. `P01308`). |

### Sample: search + diversify

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -c cookies.txt -b cookies.txt \
  -d '{
    "message": "Find a small human protein and propose 3 more stable variants"
  }'
```

### Sample: known accession in the message

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -c cookies.txt -b cookies.txt \
  -d '{
    "message": "Propose 2 more stable variants of P01308 and fold them"
  }'
```

### Sample: follow-up (same session)

Reuse `cookies.txt` so the `protdap_session` cookie carries history:

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -c cookies.txt -b cookies.txt \
  -d '{
    "message": "Fold the first candidate and report its mean pLDDT"
  }'
```

### Response shape (`ChatResponse`)

```json
{
  "reply": "string — natural-language answer from the agent",
  "retrieved_proteins": [
    {
      "accession": "P01308",
      "protein_name": "Insulin",
      "organism": "Homo sapiens",
      "length": 110,
      "sequence": "MALWMR...",
      "function": "...",
      "reviewed": true
    }
  ],
  "candidates": [
    {
      "sequence": "ACDEFG...",
      "origin": "llm_proposed",
      "parent": {
        "accession": "P01308",
        "protein_name": "Insulin",
        "organism": "Homo sapiens",
        "sequence": "MALWMR..."
      },
      "identity_to_parent": 0.95,
      "method": "llm_propose",
      "model_version": "google/gemini-2.5-flash",
      "structure": {
        "available": true,
        "mean_plddt": 82.4,
        "model_source": "biolm_esmfold",
        "structure_id": "<uuid>"
      },
      "esm1v_score": null,
      "warnings": [],
      "modifications": [
        {
          "position": 27,
          "original": "F",
          "new": "Y",
          "context_before": "GERG",
          "context_after": "FYTP",
          "reason": "short rationale for this substitution"
        }
      ],
      "explanation": "short overall rationale for the candidate"
    }
  ],
  "tool_trace_summary": [
    "search_uniprot(...)",
    "propose_variants(...)",
    "fold_sequence(...)"
  ],
  "highlighted_accessions": ["P01308"]
}
```

Field notes:

| Field | What to check |
|---|---|
| `reply` | Non-empty prose; should not claim guaranteed/proven function. |
| `retrieved_proteins` | Filled when UniProt search/entry tools ran; may be `[]` if the turn only diversified an already-known parent. Full list — not only the LLM shortlist. |
| `highlighted_accessions` | From `recommend_proteins` in the tool trace; intersected with this turn's retrieved accessions (invalid ids dropped). May be `[]` if omitted or ≤1 protein retrieved. |
| `candidates[].origin` | `"retrieved"` or `"llm_proposed"`. Proposed variants must be `"llm_proposed"`. |
| `candidates[].method` | `"retrieved"` or `"llm_propose"`. |
| `candidates[].parent` | Present for proposed variants; includes parent `sequence`. |
| `candidates[].identity_to_parent` | Float in `[0, 1]` when computed. |
| `candidates[].structure` | `available: true` only after a successful fold; then `structure_id` and usually `mean_plddt` are set. |
| `candidates[].modifications` | Only for `llm_proposed` candidates; `[]` for `retrieved`. Each entry is a point substitution that was actually applied to build `sequence`, with a `position` (1-indexed) computed in code from the flanking-context match — never taken directly from the LLM. |
| `candidates[].explanation` | Only for `llm_proposed` candidates; short LLM rationale for the candidate as a whole. `null` for `retrieved`. |
| `tool_trace_summary` | Human-readable list of tools the agent called this turn. |

Optional fields on hits/candidates (`protein_name`, `function`, `gene_names`,
`go_terms`, `diseases`, `domains`, `esm1v_score`, etc.) may be `null`
depending on which tools ran and what UniProt returned.

Also expect a `Set-Cookie: protdap_session=...` on the response when using curl with `-c`/`-b`.

---

## `GET /structures/{structure_id}`

Use a `structure_id` from a candidate that has `structure.available: true`
(same server process; cache is in-memory).

```bash
# replace STRUCTURE_ID with a value from the /chat response
curl -s -o /tmp/pred.pdb -w "%{http_code}\n" \
  http://localhost:8000/structures/STRUCTURE_ID
```

**Success (200):** raw PDB text (`Content-Type: chemical/x-pdb`).  
**Missing (404):** plain-text message that the structure was not found / expired.

```bash
head -5 /tmp/pred.pdb
```

---

## `POST /fold`

Stateless, session-independent fold - no cookie needed, not tied to any
`/chat` conversation. Used by the frontend to fold a retrieved protein
on demand without going through the agent.

```bash
curl -s -X POST http://localhost:8000/fold \
  -H 'Content-Type: application/json' \
  -d '{"sequence": "MALWMRLLPLLALLALWGPDPAAAFVNQHLCGSHLVEALYLVCGERGFFYTPKT", "name": "insulin_test"}'
```

**Success (200):**
```json
{"available": true, "mean_plddt": 67.3, "model_source": "BioLM ESMFold", "structure_id": "insulin_test_..."}
```

**Invalid input (400):** `sequence` shorter than 10 residues, or containing
characters outside the 20 standard amino acid letters.

---

## Suggested smoke path

1. `GET /liveness` → `"status": "ok"`.
2. `POST /chat` with the search + diversify sample → non-empty `reply`, some `tool_trace_summary`, and usually `retrieved_proteins` and/or `candidates`.
3. If any candidate has `structure.available: true`, `GET /structures/{structure_id}` → PDB text.
4. Optional follow-up with the same `cookies.txt` → reply that reflects prior context.
5. `POST /fold` with a real sequence → `available: true` and a `structure_id` that also resolves via `GET /structures/{structure_id}`.
