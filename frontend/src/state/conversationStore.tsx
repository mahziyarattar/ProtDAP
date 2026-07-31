import { createContext, useCallback, useContext, useEffect, useMemo, useReducer } from 'react'
import type { ReactNode } from 'react'
import { ApiError, postChat } from '../api/client'
import type { Candidate, ProteinHit } from '../api/types'

export interface Turn {
  id: string
  role: 'user' | 'assistant'
  text: string
  isError?: boolean
  retrievedProteins?: ProteinHit[]
  candidates?: Candidate[]
  highlightedAccessions?: string[]
  traceSummary?: string[]
}

interface ConversationState {
  turns: Turn[]
  allRetrievedProteins: ProteinHit[]
  allCandidates: Candidate[]
  allHighlightedAccessions: string[]
  isSending: boolean
}

const STORAGE_KEY = 'protdap.conversation.v2'

const initialState: ConversationState = {
  turns: [],
  allRetrievedProteins: [],
  allCandidates: [],
  allHighlightedAccessions: [],
  isSending: false,
}

type Action =
  | { type: 'send_start'; turn: Turn }
  | { type: 'send_success'; turn: Turn }
  | { type: 'send_error'; turn: Turn }
  | { type: 'reset' }

function dedupeByKey<T>(items: T[], keyOf: (item: T) => string): T[] {
  const seen = new Map<string, T>()
  for (const item of items) {
    seen.set(keyOf(item), item)
  }
  return Array.from(seen.values())
}

function mergeRetrievedProteins(existing: ProteinHit[], incoming: ProteinHit[]): ProteinHit[] {
  return dedupeByKey([...existing, ...incoming], (protein) => protein.accession)
}

function mergeCandidates(existing: Candidate[], incoming: Candidate[]): Candidate[] {
  return dedupeByKey([...existing, ...incoming], (candidate) => candidate.sequence)
}

function mergeHighlightedAccessions(existing: string[], incoming: string[]): string[] {
  const seen = new Set(existing)
  const merged = [...existing]
  for (const accession of incoming) {
    if (!accession || seen.has(accession)) continue
    seen.add(accession)
    merged.push(accession)
  }
  return merged
}

/** Recompute accumulated panels from per-turn payloads (source of truth). */
function rebuildAccumulators(turns: Turn[]): Pick<
  ConversationState,
  'allRetrievedProteins' | 'allCandidates' | 'allHighlightedAccessions'
> {
  let allRetrievedProteins: ProteinHit[] = []
  let allCandidates: Candidate[] = []
  let allHighlightedAccessions: string[] = []
  for (const turn of turns) {
    if (turn.retrievedProteins?.length) {
      allRetrievedProteins = mergeRetrievedProteins(allRetrievedProteins, turn.retrievedProteins)
    }
    if (turn.candidates?.length) {
      allCandidates = mergeCandidates(allCandidates, turn.candidates)
    }
    if (turn.highlightedAccessions?.length) {
      allHighlightedAccessions = mergeHighlightedAccessions(
        allHighlightedAccessions,
        turn.highlightedAccessions,
      )
    }
  }
  return { allRetrievedProteins, allCandidates, allHighlightedAccessions }
}

function reducer(state: ConversationState, action: Action): ConversationState {
  switch (action.type) {
    case 'send_start':
      return { ...state, turns: [...state.turns, action.turn], isSending: true }
    case 'send_success': {
      const turns = [...state.turns, action.turn]
      return {
        ...state,
        turns,
        ...rebuildAccumulators(turns),
        isSending: false,
      }
    }
    case 'send_error':
      return { ...state, turns: [...state.turns, action.turn], isSending: false }
    case 'reset':
      return initialState
    default:
      return state
  }
}

function loadPersistedState(): ConversationState | null {
  try {
    // Prefer v2; fall back to v1 turns so refresh after upgrade keeps history.
    const raw =
      localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem('protdap.conversation.v1')
    if (!raw) return null
    const parsed = JSON.parse(raw) as ConversationState
    const turns = Array.isArray(parsed.turns) ? parsed.turns : []
    return {
      turns,
      ...rebuildAccumulators(turns),
      isSending: false,
    }
  } catch {
    return null
  }
}

function persistState(state: ConversationState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Storage can fail (quota, private mode) - the conversation still works
    // in-memory for the current tab, it just won't survive a refresh.
  }
}

function makeTurnId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/** Lazy init from localStorage - avoids the empty-state persist race that
 * wiped panel data on mount (especially under React Strict Mode). */
function getInitialState(): ConversationState {
  return loadPersistedState() ?? initialState
}

interface ConversationContextValue {
  turns: Turn[]
  allRetrievedProteins: ProteinHit[]
  allCandidates: Candidate[]
  allHighlightedAccessions: string[]
  isSending: boolean
  sendMessage: (message: string) => Promise<void>
  resetConversation: () => void
}

const ConversationContext = createContext<ConversationContextValue | null>(null)

export function ConversationProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, getInitialState)

  useEffect(() => {
    persistState(state)
  }, [state])

  const sendMessage = useCallback(async (message: string) => {
    const trimmed = message.trim()
    if (!trimmed) return

    dispatch({
      type: 'send_start',
      turn: { id: makeTurnId(), role: 'user', text: trimmed },
    })

    try {
      const response = await postChat(trimmed)
      dispatch({
        type: 'send_success',
        turn: {
          id: makeTurnId(),
          role: 'assistant',
          text: response.reply,
          retrievedProteins: response.retrieved_proteins,
          candidates: response.candidates,
          highlightedAccessions: response.highlighted_accessions ?? [],
          traceSummary: response.tool_trace_summary,
        },
      })
    } catch (error) {
      const text =
        error instanceof ApiError
          ? `Request failed (${error.status}): ${error.message}`
          : `Request failed: ${error instanceof Error ? error.message : String(error)}`
      dispatch({
        type: 'send_error',
        turn: { id: makeTurnId(), role: 'assistant', text, isError: true },
      })
    }
  }, [])

  const resetConversation = useCallback(() => {
    dispatch({ type: 'reset' })
  }, [])

  const value = useMemo<ConversationContextValue>(
    () => ({
      turns: state.turns,
      allRetrievedProteins: state.allRetrievedProteins,
      allCandidates: state.allCandidates,
      allHighlightedAccessions: state.allHighlightedAccessions,
      isSending: state.isSending,
      sendMessage,
      resetConversation,
    }),
    [state, sendMessage, resetConversation],
  )

  return <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>
}

export function useConversation(): ConversationContextValue {
  const context = useContext(ConversationContext)
  if (!context) {
    throw new Error('useConversation must be used within a ConversationProvider')
  }
  return context
}
