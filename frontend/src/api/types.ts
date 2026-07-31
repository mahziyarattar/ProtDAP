// Mirrors app/models.py exactly. Keep these two in sync manually - there is
// no shared schema generation step in this project.

export interface ChatRequest {
  message: string
}

export interface FoldRequest {
  sequence: string
  name?: string | null
}

export interface ProteinDomain {
  name: string
  start: number | null
  end: number | null
}

export interface ProteinHit {
  accession: string
  protein_name: string | null
  gene_names?: string[] | null
  organism: string | null
  organism_id?: string | null
  length: number | null
  sequence: string | null
  function: string | null
  subcellular_locations?: string[] | null
  go_terms?: string[] | null
  diseases?: string[] | null
  domains?: ProteinDomain[] | null
  reviewed: boolean | null
  score?: number | null
  retrieval_method?: string | null
  mapped_from?: string | null
  mapped_from_db?: string | null
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
  highlighted_accessions: string[]
}

export interface LivenessResponse {
  status: string
  biolm_mcp_last_check_ok: boolean | null
}
