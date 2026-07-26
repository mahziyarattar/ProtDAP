// Mirrors app/models.py exactly. Keep these two in sync manually - there is
// no shared schema generation step in this project.

export interface ChatRequest {
  message: string
}

export interface FoldRequest {
  sequence: string
  name?: string | null
}

export interface ProteinHit {
  accession: string
  protein_name: string | null
  organism: string | null
  length: number | null
  sequence: string | null
  function: string | null
  reviewed: boolean | null
}

export interface ParentInfo {
  accession: string | null
  protein_name: string | null
  organism: string | null
  sequence: string
}

export interface StructureInfo {
  available: boolean
  mean_plddt: number | null
  model_source: string | null
  structure_id: string | null
}

export interface Modification {
  position: number
  original: string
  new: string
  context_before: string | null
  context_after: string | null
  reason: string | null
}

export type CandidateOrigin = 'retrieved' | 'llm_proposed'
export type CandidateMethod = 'retrieved' | 'llm_propose'

export interface Candidate {
  sequence: string
  origin: CandidateOrigin
  parent: ParentInfo | null
  identity_to_parent: number | null
  method: CandidateMethod
  model_version: string | null
  structure: StructureInfo
  esm1v_score: number | null
  warnings: string[]
  modifications: Modification[]
  explanation: string | null
}

export interface ChatResponse {
  reply: string
  retrieved_proteins: ProteinHit[]
  candidates: Candidate[]
  tool_trace_summary: string[]
}

export interface LivenessResponse {
  status: string
  biolm_mcp_last_check_ok: boolean | null
}
