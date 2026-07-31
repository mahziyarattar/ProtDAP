import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ThemeToggle } from '../ui/ThemeToggle'
import { useConversation } from '../../state/conversationStore'
import { MessageBubble } from './MessageBubble'

export function ChatPanel() {
  const { turns, isSending, sendMessage, resetConversation } = useConversation()
  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, isSending])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!draft.trim() || isSending) return
    const message = draft
    setDraft('')
    await sendMessage(message)
  }

  return (
    <div className="flex h-full min-w-0 flex-col bg-slate-100 transition-colors duration-150 dark:bg-slate-900">
      <header className="protdap-chat-header flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 transition-colors duration-150 dark:border-slate-800 dark:bg-slate-900">
        <div className="min-w-0">
          <h1 className="text-base font-semibold leading-tight text-slate-900 dark:text-slate-100">ProtDAP</h1>
          <p className="truncate text-[11px] leading-snug text-slate-500 dark:text-slate-400">
            Protein search &amp; diversification assistant
            <span className="mx-1.5 text-slate-300 dark:text-slate-600" aria-hidden>
              ·
            </span>
            <span dir="rtl">دستیار جست‌وجو و تنوع‌بخشی پروتئین</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <ThemeToggle />
          <button
            type="button"
            onClick={resetConversation}
            className="inline-flex h-9 w-24 shrink-0 items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-500 transition-colors duration-150 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-200"
            title="New chat"
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
            <path d="M12 20h9" />
            <path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z" />
          </svg>
          New chat
        </button>
        </div>
      </header>

      <div className="min-h-0 min-w-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden px-4 py-4">
        {turns.length === 0 && (
          <div className="mx-auto mt-12 max-w-sm text-center text-sm text-slate-400 dark:text-slate-500">
            Ask about a protein, e.g. "Find a small human protein and propose 3 more stable
            variants."
          </div>
        )}
        {turns.map((turn) => (
          <MessageBubble key={turn.id} turn={turn} />
        ))}
        {isSending && (
          <div className="flex w-full items-center gap-1.5 px-2 py-2">
            <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 dark:bg-slate-500 [animation-delay:-0.2s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 dark:bg-slate-500 [animation-delay:-0.1s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 dark:bg-slate-500" />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-slate-200 bg-white p-3 transition-colors duration-150 dark:border-slate-800 dark:bg-slate-900">
        <input
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Type a message..."
          disabled={isSending}
          dir="auto"
          className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition-colors duration-150 focus:border-indigo-500 disabled:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:bg-slate-800/50"
        />
        <button
          type="submit"
          disabled={isSending || !draft.trim()}
          className="inline-flex h-9 w-24 shrink-0 items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-2.5 text-xs font-medium text-white transition-colors duration-150 hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300 dark:disabled:bg-slate-700"
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
            <path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z" />
            <path d="m21.854 2.147-10.94 10.939" />
          </svg>
          Send
        </button>
      </form>
    </div>
  )
}
