import { useMemo } from 'react'
import { useConversation } from '../../state/conversationStore'
import {
  parentAccessionsFromCandidates,
  sortProteinsWithUsedParentsFirst,
} from '../../state/proteinOrdering'
import { ProteinCard } from './ProteinCard'

export function RetrievedProteinsPanel() {
  const { allRetrievedProteins, allCandidates } = useConversation()

  const usedAccessions = useMemo(
    () => parentAccessionsFromCandidates(allCandidates),
    [allCandidates],
  )

  const orderedProteins = useMemo(
    () => sortProteinsWithUsedParentsFirst(allRetrievedProteins, usedAccessions),
    [allRetrievedProteins, usedAccessions],
  )

  return (
    <section className="flex h-full flex-col overflow-hidden">
      <h2 className="protdap-right-section flex shrink-0 items-center border-b border-slate-200 bg-white px-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Retrieved proteins ({orderedProteins.length})
      </h2>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {orderedProteins.length === 0 ? (
          <p className="text-xs text-slate-400">
            Proteins found via UniProt search will appear here.
          </p>
        ) : (
          orderedProteins.map((protein) => (
            <ProteinCard
              key={protein.accession}
              protein={protein}
              usedAsParent={usedAccessions.has(protein.accession)}
            />
          ))
        )}
      </div>
    </section>
  )
}
