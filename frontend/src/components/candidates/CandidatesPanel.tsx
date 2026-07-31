import { useConversation } from '../../state/conversationStore'
import { CandidateCard } from './CandidateCard'

export function CandidatesPanel() {
  const { allCandidates } = useConversation()

  return (
    <section className="flex h-full flex-col overflow-hidden">
      <h2 className="protdap-right-section flex shrink-0 items-center border-b border-slate-200 bg-white px-3 text-xs font-semibold uppercase tracking-wide text-slate-500 transition-colors duration-150 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
        Candidates ({allCandidates.length})
      </h2>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {allCandidates.length === 0 ? (
          <p className="text-xs text-slate-400 dark:text-slate-500">
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
