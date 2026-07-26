import { useConversation } from '../../state/conversationStore'
import { CandidateCard } from './CandidateCard'

export function CandidatesPanel() {
  const { allCandidates } = useConversation()

  return (
    <section className="flex h-full flex-col overflow-hidden">
      <h2 className="border-b border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Candidates ({allCandidates.length})
      </h2>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {allCandidates.length === 0 ? (
          <p className="text-xs text-slate-400">
            Proposed/diversified sequences will appear here.
          </p>
        ) : (
          allCandidates.map((candidate) => (
            <CandidateCard key={candidate.sequence} candidate={candidate} />
          ))
        )}
      </div>
    </section>
  )
}
