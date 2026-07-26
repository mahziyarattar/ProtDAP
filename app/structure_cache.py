"""In-memory cache mapping a structure id to its predicted PDB text.

Fresh implementation inspired by the legacy ProteinSearch cache.py pattern
(store fold results in memory, serve them back out via a structure id) but
written from scratch and without the circular-import workaround that file
needed - fold_sequence() and the FastAPI structures route both import this
module directly.
"""

import time
import uuid
from typing import Dict, Optional, Tuple

_pdb_cache: Dict[str, Tuple[str, float]] = {}


def store_structure(pdb_text: str, name_hint: str = "structure") -> str:
    """Store PDB text and return a fresh structure id."""
    safe_hint = "".join(c for c in name_hint if c.isalnum() or c in ("_", "-")) or "structure"
    structure_id = f"{safe_hint}_{uuid.uuid4().hex[:8]}"
    _pdb_cache[structure_id] = (pdb_text, time.time())
    return structure_id


def get_structure(structure_id: str) -> Optional[str]:
    entry = _pdb_cache.get(structure_id)
    return entry[0] if entry else None


def list_structures() -> list[str]:
    return list(_pdb_cache.keys())
