import { motion } from 'motion/react'

import { formatCountdown } from '../lib/format'
import type { AskError } from '../lib/types'

const TITLES: Record<AskError['kind'], string> = {
  busy: 'The model is overloaded right now',
  limited: 'Question limit reached',
  invalid: 'Check your question',
  network: 'Connection problem',
  internal: 'Something went wrong',
}

interface Props {
  error: AskError
  secondsLeft: number // until the limit lifts; 0 when there is no wait
  onRetry: (() => void) | null
}

export function ErrorNotice({ error, secondsLeft, onRetry }: Props) {
  const waiting = error.kind === 'limited' && secondsLeft > 0
  return (
    <motion.div
      className="card notice bad"
      role="alert"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <h3>{TITLES[error.kind]}</h3>
      <p>{error.message}</p>
      {waiting && (
        <p className="countdown" aria-live="off">
          You can ask again in <strong>{formatCountdown(secondsLeft)}</strong>
        </p>
      )}
      {error.kind === 'limited' && !waiting && <p className="muted">You can ask again now.</p>}
      {error.kind === 'busy' && (
        <p className="muted">
          This demo runs on a free model quota, which is sometimes overloaded. Trying again in a
          minute usually works; "Watch a recorded answer" always works.
        </p>
      )}
      {onRetry && (
        <button type="button" className="primary retry" onClick={onRetry}>
          Try again
        </button>
      )}
    </motion.div>
  )
}
