import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
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
    <div className="flex h-full flex-col bg-slate-100">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <div>
          <h1 className="text-base font-semibold text-slate-900">ProtDAP</h1>
          <p className="text-xs text-slate-500">Protein search &amp; diversification assistant</p>
        </div>
        <button
          type="button"
          onClick={resetConversation}
          className="rounded-md px-2.5 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        >
          New chat
        </button>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {turns.length === 0 && (
          <div className="mx-auto mt-12 max-w-sm text-center text-sm text-slate-400">
            Ask about a protein, e.g. "Find a small human protein and propose 3 more stable
            variants."
          </div>
        )}
        {turns.map((turn) => (
          <MessageBubble key={turn.id} turn={turn} />
        ))}
        {isSending && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-500">
              <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.2s]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.1s]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-slate-200 bg-white p-3">
        <input
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Type a message..."
          disabled={isSending}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 disabled:bg-slate-50"
        />
        <button
          type="submit"
          disabled={isSending || !draft.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          Send
        </button>
      </form>
    </div>
  )
}
