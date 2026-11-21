// Mirrors `reply_json` and the server-sent events in `src/niyam/api.py` (D64).

export const STAGES = ['extract', 'rules', 'retrieve', 'rerank', 'explain', 'verify'] as const
export type Stage = (typeof STAGES)[number]

export type Status =
  | 'not_yet_open'
  | 'open'
  | 'closed'
  | 'upcoming'
  | 'passed'
  | 'within_limit'
  | 'over_limit'
  | 'not_applicable'
  | 'ended'

export interface Finding {
  rule: string
  citation: string
  summary: string
  status: Status
  opens: string | null
  closes: string | null
  assumptions: string[]
}

export interface Provision {
  citation: string
  headings: string[]
  body: string
}

// `greeting` and `unrelated` replies carry only fixed text in `explanation` (D72).
export type ReplyKind = 'question' | 'greeting' | 'unrelated'

export interface Reply {
  kind: ReplyKind
  question: string
  facts: Record<string, unknown>
  out_of_scope: string[]
  findings: Finding[]
  missing: string[]
  provisions: Provision[]
  explanation: string | null
  citations: string[]
  withheld_reason: string | null
  rerank_failed: boolean
  trace_id?: string | null
  disclaimer: string
  not_covered: string
}

export const MAX_HISTORY_TURNS = 6

export interface HistoryTurn {
  question: string
  answer: string | null
}

export interface ConversationTurn {
  id: number
  message: string
  reply: Reply
  asOf: string
  times: StageTimes
}

export type StageTimes = Partial<Record<Stage, number>>

export type AskErrorKind = 'busy' | 'internal' | 'limited' | 'invalid' | 'network'

export class AskError extends Error {
  readonly kind: AskErrorKind
  readonly retryAfterSeconds: number | null

  constructor(kind: AskErrorKind, message: string, retryAfterSeconds: number | null = null) {
    super(message)
    this.kind = kind
    this.retryAfterSeconds = retryAfterSeconds
  }
}
