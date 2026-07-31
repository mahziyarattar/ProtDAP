# ProTrek local service (+ ProtDAP consumer)

ProTrek is a **general local FastAPI service** (sibling checkout). ProtDAP calls
it over HTTP and enriches hits with UniProt.

## Honest note: not human-only

The published **Swiss-Prot** FAISS index is **multi-organism**. Do **not**
prefill `organism_id=9606`. Prefer optional **post-enrichment** filter on the
ProtDAP tool when the user wants human proteins.

## Status

| Item | State |
| --- | --- |
| Local weights + sequence FAISS + FastAPI `:8090` | Done (text FAISS lazy) |
| ProtDAP `search_protrek` (text→seq + UniProt enrich, soft-fail) | Done |
| Organism post-filter (`organism_id`) | Supported on the tool |
| 20-case flow eval | `python -m app.eval.protrek_flow_eval` |
| UniProt BLAST | Separate doc later |

## Run ProTrek service

```bash
cd "/mnt/c/Users/ASUS/Desktop/Python Projects/ProTrek"
bash service/run.sh
# http://127.0.0.1:8090/docs
```

## ProtDAP wiring

Set in `.env`:

```text
PROTREK_BASE_URL=http://127.0.0.1:8090
```

Tool: `search_protrek(description, k, organism_id)` — MVP is **text→sequence**
only. Enriches **all** `k` hits via `get_uniprot_entry`; skips UniProt misses.

Flow eval (service must be up):

```bash
cd ProtDAP
PROTREK_BASE_URL=http://127.0.0.1:8090 python -m app.eval.protrek_flow_eval
```

See sibling `ProTrek/service/README.md` and `SWAGGER_EXAMPLES.md`.
