import type { ChatResponse, LivenessResponse, StructureInfo } from './types'

// Relative paths, proxied to the FastAPI backend by Vite in dev (see
// vite.config.ts) so the browser treats these as same-origin requests and
// the httponly session cookie (app/session.py) is sent automatically.
// credentials: 'include' is kept explicit anyway so this client also works
// unproxied against a backend on a different origin (see the CORSMiddleware
// added in app/main.py for that case).

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

export interface ChatStreamHandlers {
  onStatus?: (message: string) => void
  onToken?: (delta: string) => void
  onDone?: (response: ChatResponse) => void
  onError?: (detail: string) => void
}

async function parseErrorBody(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string') return data.detail
    return JSON.stringify(data)
  } catch {
    return response.statusText || `HTTP ${response.status}`
  }
}

/** Non-streaming chat (kept for API clients / curl; the UI uses postChatStream). */
export async function postChat(message: string): Promise<ChatResponse> {
  const response = await fetch('/chat', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response))
  }

  return (await response.json()) as ChatResponse
}

function dispatchSseEvent(
  eventName: string,
  data: string,
  handlers: ChatStreamHandlers,
): { done: boolean; error?: string } {
  let parsed: unknown
  try {
    parsed = JSON.parse(data)
  } catch {
    return { done: false }
  }

  if (eventName === 'status') {
    const message = (parsed as { message?: unknown }).message
    if (typeof message === 'string') handlers.onStatus?.(message)
    return { done: false }
  }
  if (eventName === 'token') {
    const delta = (parsed as { delta?: unknown }).delta
    if (typeof delta === 'string' && delta) handlers.onToken?.(delta)
    return { done: false }
  }
  if (eventName === 'done') {
    handlers.onDone?.(parsed as ChatResponse)
    return { done: true }
  }
  if (eventName === 'error') {
    const detail = (parsed as { detail?: unknown }).detail
    const message = typeof detail === 'string' ? detail : 'Stream failed'
    handlers.onError?.(message)
    return { done: true, error: message }
  }
  return { done: false }
}

/**
 * Streaming chat via POST /chat/stream (SSE). EventSource cannot POST, so
 * this uses fetch + a ReadableStream reader and parses SSE frames manually.
 */
export async function postChatStream(
  message: string,
  handlers: ChatStreamHandlers,
): Promise<void> {
  const response = await fetch('/chat/stream', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ message }),
  })

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response))
  }
  if (!response.body) {
    throw new ApiError(500, 'Streaming response had no body')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let sawTerminal = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE events are separated by a blank line.
    let separator = buffer.indexOf('\n\n')
    while (separator !== -1) {
      const rawEvent = buffer.slice(0, separator)
      buffer = buffer.slice(separator + 2)

      let eventName = 'message'
      const dataLines: string[] = []
      for (const line of rawEvent.split('\n')) {
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trimStart())
        }
      }
      if (dataLines.length > 0) {
        const result = dispatchSseEvent(eventName, dataLines.join('\n'), handlers)
        if (result.done) {
          sawTerminal = true
          // error events already invoked onError; do not rethrow (avoids double UI update)
          return
        }
      }

      separator = buffer.indexOf('\n\n')
    }
  }

  if (!sawTerminal) {
    throw new ApiError(500, 'Stream ended without a done event')
  }
}

// On-demand fold for a retrieved (non-candidate) protein, bypassing the
// chat/agent loop entirely (see POST /fold in app/main.py). The result is
// kept purely in frontend component state - it is never sent back to the
// backend session or merged into the conversation store.
export async function foldSequence(sequence: string, name?: string): Promise<StructureInfo> {
  const response = await fetch('/fold', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sequence, name }),
  })

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response))
  }

  return (await response.json()) as StructureInfo
}

export function getStructureUrl(structureId: string): string {
  return `/structures/${encodeURIComponent(structureId)}`
}

export async function getStructureText(structureId: string): Promise<string> {
  const response = await fetch(getStructureUrl(structureId), {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response))
  }

  return response.text()
}

export async function getLiveness(): Promise<LivenessResponse> {
  const response = await fetch('/liveness', { credentials: 'include' })

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorBody(response))
  }

  return (await response.json()) as LivenessResponse
}
