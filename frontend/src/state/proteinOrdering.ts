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

/**
 * Panel order: recommended (highlighted) first, then used-as-parent,
 * then the rest. Relative order within each bucket is preserved.
 */
export function sortProteinsForPanel(
  proteins: ProteinHit[],
  highlightedAccessions: Set<string>,
  usedAccessions: Set<string>,
): ProteinHit[] {
  const recommended: ProteinHit[] = []
  const used: ProteinHit[] = []
  const rest: ProteinHit[] = []
  for (const protein of proteins) {
    if (highlightedAccessions.has(protein.accession)) {
      recommended.push(protein)
    } else if (usedAccessions.has(protein.accession)) {
      used.push(protein)
    } else {
      rest.push(protein)
    }
  }
  return [...recommended, ...used, ...rest]
}
