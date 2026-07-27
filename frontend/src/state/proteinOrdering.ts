import type { Candidate, ProteinHit } from '../api/types'

/** Accessions that appear as `candidate.parent` - i.e. proteins the agent diversified. */
export function parentAccessionsFromCandidates(candidates: Candidate[]): Set<string> {
  const accessions = new Set<string>()
  for (const candidate of candidates) {
    const accession = candidate.parent?.accession
    if (accession) accessions.add(accession)
  }
  return accessions
}

/** Pin agent-used parents to the top; preserve relative order within each group. */
export function sortProteinsWithUsedParentsFirst(
  proteins: ProteinHit[],
  usedAccessions: Set<string>,
): ProteinHit[] {
  const used: ProteinHit[] = []
  const rest: ProteinHit[] = []
  for (const protein of proteins) {
    if (usedAccessions.has(protein.accession)) used.push(protein)
    else rest.push(protein)
  }
  return [...used, ...rest]
}
