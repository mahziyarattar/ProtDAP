import ReactMarkdown from 'react-markdown'
import type { Turn } from '../../state/conversationStore'
import { TraceDetails } from './TraceDetails'

interface MessageBubbleProps {
  turn: Turn
}

export function MessageBubble({ turn }: MessageBubbleProps) {
  const isUser = turn.role === 'user'

  // User: indigo rounded bubble on the right.
  // Assistant: frameless full-width transcript text (no border/background box).
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-indigo-600 px-4 py-2.5 text-sm text-white">
          <div dir="auto" className="chat-markdown chat-markdown-user">
            <ReactMarkdown
              components={{
                code: ({ children, ...props }) => (
                  <code dir="ltr" className="ltr-isolate" {...props}>
                    {children}
                  </code>
                ),
              }}
            >
              {turn.text}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full px-2 text-sm">
      <div
        dir="auto"
        className={`chat-markdown ${turn.isError ? 'text-red-700' : 'text-slate-800'}`}
      >
        <ReactMarkdown
          components={{
            code: ({ children, ...props }) => (
              <code dir="ltr" className="ltr-isolate" {...props}>
                {children}
              </code>
            ),
          }}
        >
          {turn.text}
        </ReactMarkdown>
      </div>
      {turn.traceSummary && <TraceDetails traceSummary={turn.traceSummary} />}
    </div>
  )
}
