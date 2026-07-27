import { CandidatesPanel } from '../candidates/CandidatesPanel'
import { ChatPanel } from '../chat/ChatPanel'
import { RetrievedProteinsPanel } from '../proteins/RetrievedProteinsPanel'
import { StructuresExpandedView } from '../structure/StructuresExpandedView'
import { StructuresPanel } from '../structure/StructuresPanel'
import { useStructures, type RightPanelTab } from '../../state/structuresStore'

const TABS: { id: RightPanelTab; label: string }[] = [
  { id: 'proteins', label: 'Proteins' },
  { id: 'candidates', label: 'Candidates' },
  { id: 'structures', label: 'Structures' },
]

export function AppShell() {
  const { activeTab, setActiveTab, selectedIds, isExpanded } = useStructures()

  if (isExpanded) {
    return <StructuresExpandedView />
  }

  return (
    <div className="grid h-screen w-screen grid-cols-1 overflow-hidden lg:grid-cols-[1fr_380px]">
      <div className="min-h-0">
        <ChatPanel />
      </div>
      <div className="hidden min-h-0 flex-col border-l border-slate-200 bg-white lg:flex">
        <div className="protdap-right-tabs flex shrink-0 border-b border-slate-200">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id
            const badge =
              tab.id === 'structures' && selectedIds.length > 0 ? selectedIds.length : null
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`relative flex h-full flex-1 items-center justify-center px-2 text-xs font-medium transition-colors ${
                  isActive
                    ? 'border-b-2 border-indigo-600 text-indigo-700'
                    : 'border-b-2 border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                {tab.label}
                {badge !== null && (
                  <span className="ml-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-indigo-100 px-1 text-[10px] text-indigo-700">
                    {badge}
                  </span>
                )}
              </button>
            )
          })}
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          {activeTab === 'proteins' && <RetrievedProteinsPanel />}
          {activeTab === 'candidates' && <CandidatesPanel />}
          {activeTab === 'structures' && <StructuresPanel />}
        </div>
      </div>
    </div>
  )
}
