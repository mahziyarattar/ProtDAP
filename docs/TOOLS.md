# ProtDAP tools reference

Parameter and return shapes for every tool ProtDAP uses: LangChain agent
wrappers, underlying Python helpers, and BioLM MCP remote tools.

For why tools feed a private trace (not LLM prose) into structured
`candidates` / `retrieved_proteins`, see [ARCHITECTURE.md](ARCHITECTURE.md).
For curl smoke checks, see [TESTING.md](TESTING.md).

**Naming:** In `app/agent/graph.py`, LangChain registers wrappers named
`*_tool` (e.g. `search_uniprot_tool`). Trace entries, prompts, and this
doc use the logical names without that suffix (`search_uniprot`, …).

---

## 1. Agent tools (LangChain)

Defined in `app/agent/graph.py`. Each call appends
`{"tool", "args", "result"}` to the request-private trace, then returns a
**JSON string** to the LLM. Trace `result` is the raw Python object below.

### `search_uniprot`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `text` | `str` | yes (agent) | — |
| `size` | `int \| null` | no | `null` → `DEFAULT_RESULT_SIZE` (config, usually 5); clamped to `MAX_RESULT_SIZE` (20) |
| `reviewed` | `bool` | no | `true` |
| `organism_id` | `str \| null` | no | `null` |

**Return (to LLM):** JSON list of protein hits (see §2 `search_uniprot`).
On UniProt/network failure: JSON `{"error": "...", "results": []}` (no HTTP 500).

**Side effects:** HTTPS to UniProt; one trace entry (empty result + `meta.error` on soft-fail).

The system prompt tells the agent to pass `size=10` for vague/broad queries
(e.g. "a human protein") so it has enough real candidates to pick a good
match from, and to leave the default `size=5` for specific queries (e.g. an
accession or named gene). `retrieved_proteins` in the `/chat` response
reflects every hit from a search, not just whichever one is later used as a
`propose_variants` parent — so a vague query surfaces more "candidates
considered" in the response, by design.

**Example:**
```text
search_uniprot(text="human insulin", size=3, reviewed=true, organism_id="9606")
```

---

### `get_uniprot_entry`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `accession` | `str` | yes | — |

**Return (to LLM):** JSON object — one protein hit.
On UniProt/network failure: JSON `{"error": "...", "accession": "..."}` (no HTTP 500).

**Side effects:** HTTPS to UniProt; one trace entry (null result + `meta.error` on soft-fail).

**Example:**
```text
get_uniprot_entry(accession="P01308")
```

---

### `map_to_uniprot`

See [IDMAPPING.md](IDMAPPING.md) for full detail.

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `ids` | `list[str]` | yes | — (clamped to 20) |
| `from_db` | enum | yes | — one of `Gene_Name`, `Ensembl_Protein`, `RefSeq_Protein`, `PDB`, `UniProtKB_AC-ID` |
| `organism_id` | `str \| null` | no | `null` (UniProt `taxId` + post-filter) |
| `reviewed` | `bool` | no | `true` (Swiss-Prot only) |

**Return (to LLM):** JSON bundle with `proteins` (enriched), `mappings`,
`failed_ids`, `skipped_accessions`.
On UniProt/network failure: same keys with empty lists plus `error` (no HTTP 500).

**Side effects:** HTTPS to UniProt ID Mapping + per-hit `get_uniprot_entry`;
one trace entry (`tool: map_to_uniprot`, result = protein list; empty +
`meta.error` on soft-fail).

**Example:**
```text
map_to_uniprot(ids=["INS"], from_db="Gene_Name", organism_id="9606")
map_to_uniprot(ids=["ENSP00000233114"], from_db="Ensembl_Protein")
```

---

### `propose_variants`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `parent_sequence` | `str` | yes | — |
| `parent_name` | `str` | yes | — |
| `instruction` | `str` | yes | — |
| `n` | `int` | no | `3` (clamped to 1–5 in the helper) |

**Return (to LLM):** JSON list of proposed candidates (see §2).

**Side effects:** Separate OpenRouter LLM call; one trace entry. Does **not**
set identity or structure (assembler does later).

**Example:**
```text
propose_variants(parent_sequence="MALW...", parent_name="Insulin", instruction="increase thermal stability", n=3)
```

---

### `fold_sequence`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `sequence` | `str` | yes | — |
| `name` | `str` | no | `"candidate"` |

**Return (to LLM):** JSON object:
```json
{
  "structure_available": true,
  "model_source": "BioLM ESMFold",
  "mean_plddt": 82.4,
  "structure_id": "candidate_a1b2c3d4"
}
```
On failure: `structure_available=false`, `mean_plddt`/`structure_id` may be
`null`, `model_source` explains the error. Never raises to the agent.

**Side effects:** Spawns BioLM MCP (`npx @biolm/biolm-mcp`) per call; on
success stores PDB in the in-memory structure cache (§4); one trace entry.

**Example:**
```text
fold_sequence(sequence="MALWMRLL...", name="insulin_v1")
```

---

### `score_variant`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `sequence` | `str` | yes | — |

**Return (to LLM):** JSON `{"score": <number|null>}`. Usually `null` today —
BioLM ESM-1v expects a single `<mask>` in the sequence; plain full sequences
fail and are swallowed (see [ARCHITECTURE.md](ARCHITECTURE.md) future work).

**Side effects:** Fresh BioLM MCP spawn per call; one trace entry. Never blocks
the pipeline.

**Example:**
```text
score_variant(sequence="MALWMRLL...")
```

---

### `recommend_proteins`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `accessions` | `list[str]` | yes | — |
| `reason` | `str \| null` | no | `null` |

**Return (to LLM):** JSON `{"recommended": [...], "reason": ...}`.

**Side effects:** One trace entry. Does **not** change `retrieved_proteins`.
The assembler intersects recommended accessions with this turn's retrieved set
and exposes them as `ChatResponse.highlighted_accessions`. Invalid / unknown
ids are dropped silently.

**When:** Prompt requires a call whenever this turn retrieved **more than one**
protein. Skip when only one hit was retrieved. If the model skips anyway, the
UI shows all proteins undimmed.

**Example:**
```text
recommend_proteins(accessions=["P01308", "P01315"], reason="human insulin family")
```

---

## 2. Python helpers (`app/tools/`)

Independently testable; LangChain wrapping lives only in `graph.py`.

### `search_uniprot` — `app/tools/uniprot.py`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `text` | `str \| null` | one of `text`/`query` | `null` |
| `query` | `str \| null` | one of `text`/`query` | `null` |
| `size` | `int \| null` | no | `null` → config `default_result_size`; clamped to `[1, MAX_RESULT_SIZE]` (20) |
| `reviewed` | `bool` | no | `true` |
| `organism_id` | `str \| null` | no | `null` |

**Return:** `List[Dict]` — each hit:
`accession`, `protein_name`, `gene_names`, `organism`, `organism_id`,
`length`, `sequence`, `function`, `subcellular_locations`, `go_terms`,
`diseases`, `domains`, `reviewed`. Annotation lists are capped
(`gene_names`≤5, locations≤8, GO≤10, diseases≤5, domains≤8) so agent
context stays small. Missing annotations are `null`.

**Side effects:** `GET {uniprot_base_url}/uniprotkb/search`; one retry on HTTP
429. Raises `ValueError` if neither `text` nor `query`; `UniProtResponseError`
on bad shape.

**Example:**
```python
await search_uniprot(text="insulin", organism_id="9606", size=5)
```

### `get_uniprot_entry` — `app/tools/uniprot.py`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `accession` | `str` | yes | — |

**Return:** One hit dict (same fields as above).

**Side effects:** `GET .../uniprotkb/{accession}.json`. Raises
`UniProtResponseError` if `primaryAccession` missing.

### `build_query` — `app/tools/uniprot.py`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `text` | `str \| null` | one of `text`/`query` | `null` |
| `query` | `str \| null` | one of `text`/`query` | `null` |
| `reviewed` | `bool` | no | `true` |
| `organism_id` | `str \| null` | no | `null` |

**Return:** Lucene-style UniProt query string, e.g.
`(insulin) AND (reviewed:true) AND (organism_id:9606)`.

**Side effects:** None.

---

### `propose_variants` — `app/tools/generation.py`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `parent_sequence` | `str` | yes | — |
| `parent_name` | `str` | yes | — |
| `instruction` | `str` | yes | — |
| `n` | `int` | no | `3` (clamped 1–`MAX_CANDIDATES`=5) |

**Return:** `List[Dict]`, each:
```json
{
  "sequence": "...",
  "modifications": [
    {
      "position": 12,
      "original": "A",
      "new": "V",
      "context_before": "GERG",
      "context_after": "FYTP",
      "reason": "..."
    }
  ],
  "explanation": "...",
  "origin": "llm_proposed",
  "method": "llm_propose",
  "model_version": "<openrouter_model>"
}
```
The LLM itself never provides `position` or the final `sequence` — it only
proposes modifications as `context_before`/`original`/`new`/`context_after`
(exact flanking text from the parent). `_apply_modifications` locates each
one by requiring `context_before + original + context_after` to match the
parent sequence exactly once, then builds `sequence` and computes the
1-indexed `position` from the match — this is why `modifications` here only
ever contains entries that were actually applied (mismatched/ambiguous ones
are silently dropped, not the whole candidate). This same dict (minus
`sequence`/`origin`/`method`/`model_version`) becomes each
`Candidate.modifications[]` entry in the `/chat` response (see [TESTING.md](TESTING.md));
`explanation` likewise becomes `Candidate.explanation`. Invalid / too-short
sequences after AA cleaning, exact duplicates within the batch, and
candidates identical to the parent are dropped. Empty list if the LLM JSON
cannot be parsed.

**Side effects:** Dedicated OpenRouter chat completion (`temperature=0.7`).

---

### `compute_identity` — `app/tools/identity.py`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `parent_sequence` | `str` | yes | — |
| `candidate_sequence` | `str` | yes | — |

**Return:** `float` in `[0.0, 1.0]` — identities / aligned length (global
PairwiseAligner). Empty input → `0.0`.

**Side effects:** None (used by the assembler, not exposed to the agent).

**Example:**
```python
compute_identity("ACDEFG", "ACDYFG")  # ~0.83 depending on gaps
```

---

### BioLM client — `app/tools/biolm_mcp.py`

#### `get_biolm_client(biolm_token: str) -> BioLMMCPClient`

Module singleton. Safe across asyncio tasks (no shared open connection).

#### `BioLMMCPClient.check_connection() -> bool`

No params. Spawns MCP, handshakes, closes. Sets `last_check_ok`. Used at
startup / `GET /liveness`.

#### `BioLMMCPClient.fold_sequence(sequence: str, name: str) -> Dict`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `sequence` | `str` | yes | — |
| `name` | `str` | yes | — (agent default `"candidate"`) |

**Return / side effects:** Same as agent `fold_sequence`; calls MCP
`predict_v3_esmfold` with `{"items": [{"sequence": ...}]}`; may call
`store_structure`.

#### `BioLMMCPClient.score_variant(sequence: str) -> Dict`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `sequence` | `str` | yes | — |

**Return:** `{"score": number | null}`. Calls MCP `predict_v3_esm1v_all`.

#### `reset_biolm_client() -> None`

Clears the singleton (tests). No params / return.

---

## 3. BioLM MCP remote tools

Spawned via `npx -y @biolm/biolm-mcp` over stdio. Env: `BIOLMAI_TOKEN`.
ProtDAP opens a **fresh connection per call** (see reliability note in
[ARCHITECTURE.md](ARCHITECTURE.md)).

### `predict_v3_esmfold`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `items` | `array[{sequence: str}]` | no (schema); ProtDAP always sends it | — |
| `jq_filter` | `str` | no | omitted by ProtDAP |

**Return (BioLM):** roughly
`{"results": [{"mean_plddt": number, "pdb": string, "ptm": number}, ...]}`.
Client unwraps `results[0]`.

**Side effects:** Hosted BioLM fold; ProtDAP then caches `pdb` if present.

**Example (as ProtDAP sends):**
```json
{"items": [{"sequence": "MALWMRLLPLLALLALWGPDPAAA"}]}
```

---

### `predict_v3_esm1v_all`

| Param | Type | Required | Default |
| --- | --- | --- | --- |
| `items` | `array[{sequence: str}]` | no (schema); ProtDAP always sends it | — |
| `params` | `object` | no | omitted by ProtDAP |
| `jq_filter` | `str` | no | omitted by ProtDAP |

**Return (BioLM):** `results[]` with per-model arrays (`esm1v-n1` … `n5`) of
`{token, score, sequence, token_str}`. Client looks for
`score` / `mean_score` / `pseudo_log_likelihood` on the unwrapped item.

**Side effects:** Hosted BioLM scoring. Needs exactly one `<mask>` in
`sequence` for a valid point-mutation score; ProtDAP currently passes the
full candidate and typically gets `score=null`.

**Example (valid BioLM usage, not yet wired end-to-end):**
```json
{"items": [{"sequence": "MALWMRLLP<mask>LALLALWGPDPAAA"}]}
```

---

## 4. Structure cache (`app/structure_cache.py`)

Not an agent tool; used by `fold_sequence`, `POST /fold` (a stateless,
session-independent HTTP endpoint in `app/main.py` that lets the frontend
fold an arbitrary sequence - e.g. a retrieved protein - without going
through the agent/chat loop at all), and `GET /structures/{id}`.

### `store_structure(pdb_text: str, name_hint: str = "structure") -> str`

Returns id like `{sanitized_hint}_{8 hex}`. Writes in-memory `_pdb_cache`.

### `get_structure(structure_id: str) -> str | None`

### `list_structures() -> list[str]`

**Side effects:** Process-local only; lost on restart. No TTL eviction in v1.
