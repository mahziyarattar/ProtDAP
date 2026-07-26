import { useConversation } from '../../state/conversationStore'
import { ProteinCard } from './ProteinCard'

export function RetrievedProteinsPanel() {
  const { allRetrievedProteins } = useConversation()

  return (
    <section className="flex h-full flex-col overflow-hidden">
      <h2 className="border-b border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Retrieved proteins ({allRetrievedProteins.length})
      </h2>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {allRetrievedProteins.length === 0 ? (
          <p className="text-xs text-slate-400">
            Proteins found via UniProt search will appear here.
          </p>
        ) : (
          allRetrievedProteins.map((protein) => (
            <ProteinCard key={protein.accession} protein={protein} />
          ))
        )}
      </div>
    </section>
  )
}
