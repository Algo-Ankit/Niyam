import { motion } from 'motion/react'

import type { AskError } from '../lib/types'

const TITLES: Record<AskError['kind'], string> = {
  busy: 'The assistant is resting',
  limited: 'Slow down a little',
  invalid: 'Check your question',
  network: 'Connection problem',
  internal: 'Something went wrong',
}

export function ErrorNotice({ error }: { error: AskError }) {
  const minutes = error.retryAfterSeconds ? Math.ceil(error.retryAfterSeconds / 60) : null
  return (
    <motion.div
      className="card notice bad"
      role="alert"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <h3>{TITLES[error.kind]}</h3>
      <p>{error.message}</p>
      {minutes !== null && (
        <p className="muted">
          You can ask again in about {minutes} minute{minutes === 1 ? '' : 's'}.
        </p>
      )}
      {(error.kind === 'busy' || error.kind === 'limited') && (
        <p className="muted">
          This demo runs on free model quotas. "Watch a recorded answer" still works.
        </p>
      )}
    </motion.div>
  )
}
