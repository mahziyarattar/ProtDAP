# UniProt ID Mapping for ProtDAP

Maps external identifiers / gene symbols to **UniProtKB**. Prefers the
`/idmapping/uniprotkb/results/{jobId}` payload (full entries embedded in
`to`); falls back to `get_uniprot_entry` only when `to` is a bare accession
string.

API: [UniProt ID Mapping](https://www.uniprot.org/help/id_mapping) —
`https://rest.uniprot.org/idmapping`.

---

## Tool: `map_to_uniprot`

| Param | Type | Required | Notes |
| --- | --- | --- | --- |
| `ids` | `list[str]` | yes | Max 20 after dedupe/trim |
| `from_db` | enum | yes | LLM must choose; no code auto-detect |
| `organism_id` | `str \| null` | no | Sent as UniProt `taxId` on submit (esp. for `Gene_Name`); also post-filter |
| `reviewed` | `bool` | no | Default `true` — Swiss-Prot only (skip TrEMBL) |

### Allowed `from_db` (whitelist)

| Value | Example ids |
| --- | --- |
| `Gene_Name` | `INS`, `BRCA1` |
| `Ensembl_Protein` | `ENSP00000233114` |
| `RefSeq_Protein` | `NP_000207` |
| `PDB` | `4HHB` |
| `UniProtKB_AC-ID` | `P01308` |

Always maps **to** `UniProtKB`. If the agent is unsure which `from_db` fits,
it should **ask the user** — not guess.

### Return shape

```json
{
  "proteins": [
    {
      "accession": "P01308",
      "protein_name": "Insulin",
      "organism": "Homo sapiens",
      "organism_id": "9606",
      "length": 110,
      "sequence": "...",
      "function": "...",
      "reviewed": true,
      "retrieval_method": "uniprot_idmapping",
      "mapped_from": "INS",
      "mapped_from_db": "Gene_Name"
    }
  ],
  "mappings": [{"from": "INS", "to": "P01308"}],
  "failed_ids": [],
  "skipped_accessions": []
}
```

- Soft-fail: UniProt enrich misses, organism mismatches, and (by default)
  unreviewed TrEMBL hits are skipped, not fatal.
- For gene symbols, prefer `organism_id` (e.g. `"9606"`) — without `taxId`, Gene_Name maps across many organisms.
- Assembler puts `proteins` into `retrieved_proteins` (dedupe by accession).

---

## When to use which tool

| User input | Tool |
| --- | --- |
| Clear gene symbol / Ensembl / RefSeq / PDB / UniProt id | `map_to_uniprot` |
| Keyword / named protein phrase | `search_uniprot` |
| Vague functional description | `search_protrek` |
| Already have UniProt accession only | `get_uniprot_entry` |
| Amino-acid sequence homology | UniProt BLAST (not yet) |

---

## Implementation

- Client: `app/tools/uniprot_idmapping.py`
- Agent wrapper: `map_to_uniprot_tool` in `app/agent/graph.py`
- Job flow: `POST /idmapping/run` → poll `/idmapping/status/{jobId}` (60s cap) →
  `/idmapping/uniprotkb/results/{jobId}` (fallback `/idmapping/results/{jobId}`)

---

## Sample chat queries (manual UI / `/chat` tests)

Paste these into the frontend or `POST /chat`. Expect the agent to call
`map_to_uniprot` (not `search_uniprot` / `search_protrek`) when the id type
is clear. Prefer human filter when the user says human / انسان.

### English

| Intent | Sample query | Expected `from_db` |
| --- | --- | --- |
| Gene symbol | Map gene **INS** to UniProt for human. | `Gene_Name` |
| Gene symbol | Look up UniProt entries for human genes **BRCA1** and **TP53**. | `Gene_Name` |
| Ensembl | Resolve Ensembl protein **ENSP00000233114** to UniProt. | `Ensembl_Protein` |
| RefSeq | Map RefSeq protein **NP_000207** to UniProtKB. | `RefSeq_Protein` |
| PDB | What UniProt accession corresponds to PDB **4HHB**? | `PDB` |
| UniProt AC | Resolve UniProt accession **P01308** via ID mapping. | `UniProtKB_AC-ID` |
| Ambiguous (should ask) | Map **12345** to UniProt. | ask user which `from_db` |

### Persian (فارسی)

| Intent | Sample query | Expected `from_db` |
| --- | --- | --- |
| Gene symbol | ژن **INS** را برای انسان به یونی‌پروت مپ کن. | `Gene_Name` |
| Gene symbol | شناسه‌های یونی‌پروت ژن‌های انسانی **BRCA1** و **TP53** را پیدا کن. | `Gene_Name` |
| Ensembl | شناسه Ensembl پروتئین **ENSP00000233114** را به UniProt تبدیل کن. | `Ensembl_Protein` |
| RefSeq | RefSeq پروتئین **NP_000207** را به UniProtKB مپ کن. | `RefSeq_Protein` |
| PDB | کدام accession یونی‌پروت با PDB **4HHB** متناظر است؟ | `PDB` |
| UniProt AC | accession یونی‌پروت **P01308** را با ID mapping resolve کن. | `UniProtKB_AC-ID` |
| Ambiguous (should ask) | **12345** را به یونی‌پروت مپ کن. | از کاربر بپرسد کدام `from_db` |

Quick check after a turn: `tool_trace_summary` should mention `map_to_uniprot`,
and hits should use `retrieval_method: uniprot_idmapping`.

---

## Smoke (manual)

```bash
cd ProtDAP
.venv/bin/python - <<'PY'
import asyncio
from app.tools.uniprot_idmapping import map_to_uniprot

async def main():
    out = await map_to_uniprot(["INS"], from_db="Gene_Name", organism_id="9606")
    print(out["mappings"])
    print([(p["accession"], p["organism"]) for p in out["proteins"]])

asyncio.run(main())
PY
```
