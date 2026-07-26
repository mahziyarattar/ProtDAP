import { ChatPanel } from '../chat/ChatPanel'
import { CandidatesPanel } from '../candidates/CandidatesPanel'
import { RetrievedProteinsPanel } from '../proteins/RetrievedProteinsPanel'

export function AppShell() {
  return (
    <div className="grid h-screen w-screen grid-cols-1 overflow-hidden lg:grid-cols-[1fr_360px]">
      <div className="min-h-0">
        <ChatPanel />
      </div>
      <div className="hidden min-h-0 flex-col divide-y divide-slate-200 border-l border-slate-200 bg-white lg:flex">
        <div className="min-h-0 flex-1 overflow-hidden">
          <RetrievedProteinsPanel />
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          <CandidatesPanel />
        </div>
      </div>
    </div>
  )
}
