import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Turn } from '../../state/conversationStore'
import { useConversation } from '../../state/conversationStore'
import { TraceDetails } from './TraceDetails'

interface MessageBubbleProps {
  turn: Turn
}

const remarkPlugins = [remarkGfm]

const userActionButtonClass =
  'inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 opacity-0 transition-all duration-150 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-700 focus:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-200'

const markdownComponents: Components = {
  code: ({ children, ...props }) => (
    <code dir="ltr" className="ltr-isolate" {...props}>
      {children}
    </code>
  ),
  // Tailwind utilities (not index.css) so spacing reliably hot-reloads under WSL.
  hr: () => (
    <hr className="mt-3 mb-0 border-0 border-t border-slate-300 pb-2 dark:border-slate-600" />
  ),
  h1: ({ children }) => <h1 className="mt-3 mb-2 text-[1.1em] font-bold leading-snug">{children}</h1>,
  h2: ({ children }) => <h2 className="mt-3 mb-2 text-[1.05em] font-bold leading-snug">{children}</h2>,
  h3: ({ children }) => <h3 className="mt-3 mb-2 font-bold leading-snug">{children}</h3>,
  h4: ({ children }) => <h4 className="mt-3 mb-1.5 font-bold leading-snug">{children}</h4>,
  h5: ({ children }) => <h5 className="mt-3 mb-1.5 font-bold leading-snug">{children}</h5>,
  h6: ({ children }) => <h6 className="mt-2 mb-1.5 font-bold leading-snug">{children}</h6>,
  table: ({ children }) => (
    <div className="my-2 w-full overflow-x-auto">
      <table className="w-full min-w-[20rem] border-collapse text-start text-[0.9em] dark:text-slate-200">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="border-b border-slate-300 bg-slate-200/70 dark:border-slate-600 dark:bg-slate-800/80">
      {children}
    </thead>
  ),
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-slate-200 last:border-b-0 dark:border-slate-700">{children}</tr>
  ),
  th: ({ children }) => (
    <th className="px-2.5 py-1.5 align-top font-semibold whitespace-nowrap">{children}</th>
  ),
  td: ({ children }) => <td className="px-2.5 py-1.5 align-top">{children}</td>,
}

const userMarkdownComponents: Components = {
  ...markdownComponents,
  hr: () => <hr className="mt-3 mb-0 border-0 border-t border-white/35 pb-2" />,
}

function UserMessageBubble({ turn }: { turn: Turn }) {
  const { sendMessage, isSending } = useConversation()
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(turn.text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard may be unavailable; ignore for this convenience action.
    }
  }

  async function handleRetry() {
    if (isSending) return
    await sendMessage(turn.text)
  }

  return (
    <div className="chat-message-enter group flex items-center justify-end gap-1.5">
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={handleCopy}
          className={userActionButtonClass}
          title={copied ? 'Copied!' : 'Copy message'}
          aria-label={copied ? 'Copied!' : 'Copy message'}
        >
          {copied ? (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-3.5 w-3.5"
              aria-hidden
            >
              <path d="M20 6 9 17l-5-5" />
            </svg>
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-3.5 w-3.5"
              aria-hidden
            >
              <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
              <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
            </svg>
          )}
        </button>
        <button
          type="button"
          onClick={handleRetry}
          disabled={isSending}
          className={userActionButtonClass}
          title="Retry message"
          aria-label="Retry message"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-3.5 w-3.5"
            aria-hidden
          >
            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
            <path d="M3 3v5h5" />
          </svg>
        </button>
      </div>
      <div className="max-w-[85%] rounded-2xl bg-indigo-600 px-4 py-2.5 text-sm text-white">
        <div dir="auto" className="chat-markdown chat-markdown-user">
          <ReactMarkdown remarkPlugins={remarkPlugins} components={userMarkdownComponents}>
            {turn.text}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  )
}

export function MessageBubble({ turn }: MessageBubbleProps) {
  const isUser = turn.role === 'user'

  // User: indigo rounded bubble on the right.
  // Assistant: frameless full-width transcript text (no border/background box).
  if (isUser) {
    return <UserMessageBubble turn={turn} />
  }

  return (
    <div className="chat-message-enter w-full min-w-0 max-w-full px-2 text-sm">
      <div
        dir="auto"
        className={`chat-markdown ${turn.isError ? 'text-red-700 dark:text-red-400' : 'text-slate-800 dark:text-slate-200'}`}
      >
        <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents}>
          {turn.text}
        </ReactMarkdown>
      </div>
      {turn.traceSummary && <TraceDetails traceSummary={turn.traceSummary} />}
    </div>
  )
}
