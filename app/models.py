"""Pydantic models for ProtDAP's HTTP API and internal data structures.

These models define the schema that the deterministic assembler (see
app/agent/assembler.py) fills in after each agent run. The LLM's own prose
never becomes structured data directly - it only becomes `ChatResponse.reply`.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str


class FoldRequest(BaseModel):
    """Body for POST /fold - an on-demand fold that bypasses the chat/agent
    loop entirely. Used by the frontend to let the user fold a retrieved
    (non-candidate) protein directly, without going through the LLM."""

    sequence: str
    name: Optional[str] = None


class ProteinHit(BaseModel):
    accession: str
    protein_name: Optional[str] = None
    organism: Optional[str] = None
    length: Optional[int] = None
    sequence: Optional[str] = None
    function: Optional[str] = None
    reviewed: Optional[bool] = None


class ParentInfo(BaseModel):
    accession: Optional[str] = None
    protein_name: Optional[str] = None
    organism: Optional[str] = None
    sequence: str


class StructureInfo(BaseModel):
    available: bool = False
    mean_plddt: Optional[float] = None
    model_source: Optional[str] = None
    structure_id: Optional[str] = None


class Modification(BaseModel):
    """A single point substitution applied to a candidate's parent sequence.

    `position` is always the real 1-indexed residue position computed in
    code from the flanking-context match (see
    app/tools/generation.py::_apply_modifications) - never taken directly
    from the LLM. Only modifications that were actually applied to produce
    `Candidate.sequence` appear here.
    """

    position: int
    original: str
    new: str
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    reason: Optional[str] = None


class Candidate(BaseModel):
    sequence: str
    origin: Literal["retrieved", "llm_proposed"]
    parent: Optional[ParentInfo] = None
    identity_to_parent: Optional[float] = None
    method: Literal["retrieved", "llm_propose"]
    model_version: Optional[str] = None
    structure: StructureInfo = Field(default_factory=StructureInfo)
    esm1v_score: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    modifications: List[Modification] = Field(default_factory=list)
    explanation: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    retrieved_proteins: List[ProteinHit] = Field(default_factory=list)
    candidates: List[Candidate] = Field(default_factory=list)
    tool_trace_summary: List[str] = Field(default_factory=list)
