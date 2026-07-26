import type { Turn } from '../../state/conversationStore'
import { TraceDetails } from './TraceDetails'

interface MessageBubbleProps {
  turn: Turn
}

export function MessageBubble({ turn }: MessageBubbleProps) {
  const isUser = turn.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
          isUser
            ? 'bg-indigo-600 text-white'
            : turn.isError
              ? 'bg-red-50 text-red-800 border border-red-200'
              : 'bg-white text-slate-800 border border-slate-200'
        }`}
      >
        {turn.text}
        {!isUser && turn.traceSummary && <TraceDetails traceSummary={turn.traceSummary} />}
      </div>
    </div>
  )
}
