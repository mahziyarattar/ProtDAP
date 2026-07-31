import { useMemo } from 'react'
import { useConversation } from '../../state/conversationStore'
import {
  parentAccessionsFromCandidates,
  sortProteinsForPanel,
} from '../../state/proteinOrdering'
import { ProteinCard } from './ProteinCard'

export function RetrievedProteinsPanel() {
  const { allRetrievedProteins, allCandidates, allHighlightedAccessions } = useConversation()

  const usedAccessions = useMemo(
    () => parentAccessionsFromCandidates(allCandidates),
    [allCandidates],
  )

  const highlightedAccessions = useMemo(
    () => new Set(allHighlightedAccessions),
    [allHighlightedAccessions],
  )

  const dimInactive = highlightedAccessions.size > 0

  const orderedProteins = useMemo(
    () =>
      sortProteinsForPanel(allRetrievedProteins, highlightedAccessions, usedAccessions),
    [allRetrievedProteins, highlightedAccessions, usedAccessions],
  )

  return (
    <section className="flex h-full flex-col overflow-hidden">
      <h2 className="protdap-right-section flex shrink-0 items-center border-b border-slate-200 bg-white px-3 text-xs font-semibold uppercase tracking-wide text-slate-500 transition-colors duration-150 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
        Retrieved proteins ({orderedProteins.length})
      </h2>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {orderedProteins.length === 0 ? (
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Proteins found via UniProt search will appear here.
          </p>
        ) : (
          orderedProteins.map((protein) => {
            const recommended = highlightedAccessions.has(protein.accession)
            return (
              <ProteinCard
                key={protein.accession}
                protein={protein}
                usedAsParent={usedAccessions.has(protein.accession)}
                recommended={recommended}
                dimmed={dimInactive && !recommended}
              />
            )
          })
        )}
      </div>
    </section>
  )
}
