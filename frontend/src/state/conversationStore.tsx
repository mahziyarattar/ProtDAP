import { createContext, useCallback, useContext, useEffect, useMemo, useReducer } from 'react'
import type { ReactNode } from 'react'
import { ApiError, postChatStream } from '../api/client'
import type { Candidate, ProteinHit } from '../api/types'

export interface Turn {
  id: string
  role: 'user' | 'assistant'
  text: string
  isError?: boolean
  isStreaming?: boolean
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
  streamStatus: string | null
  streamingAssistantId: string | null
}

const STORAGE_KEY = 'protdap.conversation.v2'

const initialState: ConversationState = {
  turns: [],
  allRetrievedProteins: [],
  allCandidates: [],
  allHighlightedAccessions: [],
  isSending: false,
  streamStatus: null,
  streamingAssistantId: null,
}

type Action =
  | { type: 'send_start'; userTurn: Turn; assistantTurn: Turn }
  | { type: 'stream_status'; status: string }
  | { type: 'stream_token'; delta: string }
  | {
      type: 'send_success'
      reply: string
      retrievedProteins: ProteinHit[]
      candidates: Candidate[]
      highlightedAccessions: string[]
      traceSummary: string[]
    }
  | { type: 'send_error'; message: string }
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

function updateAssistantTurn(
  turns: Turn[],
  assistantId: string | null,
  patch: Partial<Turn>,
): Turn[] {
  if (!assistantId) return turns
  return turns.map((turn) => (turn.id === assistantId ? { ...turn, ...patch } : turn))
}

function reducer(state: ConversationState, action: Action): ConversationState {
  switch (action.type) {
    case 'send_start':
      return {
        ...state,
        turns: [...state.turns, action.userTurn, action.assistantTurn],
        isSending: true,
        streamStatus: null,
        streamingAssistantId: action.assistantTurn.id,
      }
    case 'stream_status':
      return { ...state, streamStatus: action.status }
    case 'stream_token': {
      const assistantId = state.streamingAssistantId
      if (!assistantId) return state
      return {
        ...state,
        streamStatus: null,
        turns: state.turns.map((turn) =>
          turn.id === assistantId ? { ...turn, text: turn.text + action.delta } : turn,
        ),
      }
    }
    case 'send_success': {
      const assistantId = state.streamingAssistantId
      const turns = updateAssistantTurn(state.turns, assistantId, {
        text: action.reply,
        isStreaming: false,
        isError: false,
        retrievedProteins: action.retrievedProteins,
        candidates: action.candidates,
        highlightedAccessions: action.highlightedAccessions,
        traceSummary: action.traceSummary,
      })
      return {
        ...state,
        turns,
        ...rebuildAccumulators(turns),
        isSending: false,
        streamStatus: null,
        streamingAssistantId: null,
      }
    }
    case 'send_error': {
      const assistantId = state.streamingAssistantId
      const existing = assistantId
        ? state.turns.find((turn) => turn.id === assistantId)?.text ?? ''
        : ''
      const text = existing.trim()
        ? `${existing.trim()}\n\n${action.message}`
        : action.message
      const turns = updateAssistantTurn(state.turns, assistantId, {
        text,
        isStreaming: false,
        isError: true,
      })
      return {
        ...state,
        turns,
        isSending: false,
        streamStatus: null,
        streamingAssistantId: null,
      }
    }
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
    const turns = Array.isArray(parsed.turns)
      ? parsed.turns.map((turn) => ({ ...turn, isStreaming: false }))
      : []
    return {
      turns,
      ...rebuildAccumulators(turns),
      isSending: false,
      streamStatus: null,
      streamingAssistantId: null,
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
  streamStatus: string | null
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

    const assistantId = makeTurnId()
    dispatch({
      type: 'send_start',
      userTurn: { id: makeTurnId(), role: 'user', text: trimmed },
      assistantTurn: {
        id: assistantId,
        role: 'assistant',
        text: '',
        isStreaming: true,
      },
    })

    try {
      await postChatStream(trimmed, {
        onStatus: (status) => dispatch({ type: 'stream_status', status }),
        onToken: (delta) => dispatch({ type: 'stream_token', delta }),
        onDone: (response) =>
          dispatch({
            type: 'send_success',
            reply: response.reply,
            retrievedProteins: response.retrieved_proteins,
            candidates: response.candidates,
            highlightedAccessions: response.highlighted_accessions ?? [],
            traceSummary: response.tool_trace_summary,
          }),
        onError: (detail) => {
          dispatch({
            type: 'send_error',
            message: `Request failed: ${detail}`,
          })
        },
      })
    } catch (error) {
      const text =
        error instanceof ApiError
          ? `Request failed (${error.status}): ${error.message}`
          : `Request failed: ${error instanceof Error ? error.message : String(error)}`
      dispatch({ type: 'send_error', message: text })
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
      streamStatus: state.streamStatus,
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
