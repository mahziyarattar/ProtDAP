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

async function parseErrorBody(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string') return data.detail
    return JSON.stringify(data)
  } catch {
    return response.statusText || `HTTP ${response.status}`
  }
}

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
