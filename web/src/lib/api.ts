import { AskError, STAGES, type Reply, type Stage } from './types'

const API = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export interface Health {
  status: string
  corpus_snapshot: string | null
}

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch(`${API}/api/health`, signal ? { signal } : {})
  if (!response.ok) throw new Error(`health ${response.status}`)
  return (await response.json()) as Health
}

/** Asks the assistant; `onStage` fires as each pipeline stage finishes on the server. */
export async function ask(
  message: string,
  asOf: string,
  onStage: (stage: Stage, ms: number) => void,
  signal: AbortSignal,
): Promise<Reply> {
  let response: Response
  try {
    response = await fetch(`${API}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, as_of: asOf }),
      signal,
    })
  } catch (error) {
    if (signal.aborted) throw error
    throw new AskError('network', 'Could not reach the assistant. Check your connection.')
  }
  if (response.status === 429) {
    const retry = Number(response.headers.get('Retry-After'))
    throw new AskError('limited', await detail(response), Number.isFinite(retry) ? retry : null)
  }
  if (response.status === 422) {
    throw new AskError('invalid', 'Write between 3 and 2,000 characters.')
  }
  if (!response.ok || !response.body) {
    throw new AskError('internal', 'Something went wrong while answering. Try again later.')
  }
  return readEvents(response.body, onStage)
}

/** Sends optional thumbs up/down feedback on a live answer trace (D76). */
export async function sendFeedback(
  traceId: string,
  helpful: boolean,
  comment?: string,
): Promise<boolean> {
  const payload: { trace_id: string; helpful: boolean; comment?: string } = {
    trace_id: traceId,
    helpful,
  }
  const trimmed = comment?.trim()
  if (trimmed) payload.comment = trimmed
  try {
    const response = await fetch(`${API}/api/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) return false
    const data = (await response.json()) as { recorded?: unknown }
    return data.recorded === true
  } catch {
    return false
  }
}

async function detail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // fall through to the generic message
  }
  return 'Too many questions right now.'
}

async function readEvents(
  body: ReadableStream<Uint8Array>,
  onStage: (stage: Stage, ms: number) => void,
): Promise<Reply> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let end: number
    while ((end = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      const event = parseBlock(block)
      if (!event) continue
      if (event.name === 'stage') {
        const { stage, ms } = event.data as { stage: string; ms: number }
        if (isStage(stage)) onStage(stage, ms)
      } else if (event.name === 'reply') {
        return event.data as Reply
      } else if (event.name === 'error') {
        const { code, message } = event.data as { code: string; message: string }
        throw new AskError(code === 'busy' ? 'busy' : 'internal', message)
      }
    }
  }
  throw new AskError('network', 'The connection closed before the answer arrived.')
}

function parseBlock(block: string): { name: string; data: unknown } | null {
  let name = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) name = line.slice(7)
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  return data ? { name, data: JSON.parse(data) as unknown } : null
}

function isStage(value: string): value is Stage {
  return (STAGES as readonly string[]).includes(value)
}
