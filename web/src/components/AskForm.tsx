import { motion } from 'motion/react'
import { useState, type FormEvent, type KeyboardEvent } from 'react'

import { formatCountdown } from '../lib/format'

const EXAMPLES = [
  {
    label: 'Unemployment days',
    text: 'My program ended 2026-05-15. My OPT EAD started 2026-07-01 and I worked at Acme from 2026-08-01 to 2026-10-31. How many unemployment days have I used?',
  },
  {
    label: 'STEM extension',
    text: 'I have a STEM degree and my OPT ends 2027-03-10. When can I file for the STEM extension?',
  },
  {
    label: 'OPT filing window',
    text: 'I graduate on 2027-05-14 and my DSO recommended OPT on 2027-03-01. When can I file, and what is the latest start date?',
  },
]
const MAX = 2000

interface Props {
  busy: boolean
  blockedSeconds: number // seconds until the question limit lifts; 0 when asking is allowed
  sampleMessage: string
  onAsk: (message: string) => void
  onSample: () => void
}

export function AskForm({ busy, blockedSeconds, sampleMessage, onAsk, onSample }: Props) {
  const [message, setMessage] = useState('')
  const trimmed = message.trim()
  const valid = trimmed.length >= 3 && message.length <= MAX
  const blocked = blockedSeconds > 0
  const canAsk = valid && !busy && !blocked

  function submit(event: FormEvent) {
    event.preventDefault()
    if (canAsk) onAsk(trimmed)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) submit(event)
  }

  return (
    <form className="ask" onSubmit={submit}>
      <label htmlFor="message" className="sr-only">
        Describe your situation and ask your question
      </label>
      <div className="ask-box">
        <textarea
          id="message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="e.g. I graduated 2026-05-15 and my DSO recommended OPT on 2026-05-20. When must I file?"
          rows={4}
          maxLength={MAX}
          disabled={busy}
        />
        <div className="ask-bar">
          <span className="hint">
            Use exact dates. Don't include your SEVIS ID, passport or A-number.
          </span>
          <motion.button
            type="submit"
            className="primary"
            disabled={!canAsk}
            whileHover={canAsk ? { y: -1 } : {}}
            whileTap={canAsk ? { scale: 0.97 } : {}}
          >
            {busy
              ? 'Working…'
              : blocked
                ? `Ask again in ${formatCountdown(blockedSeconds)}`
                : 'Ask Niyam'}
            <span aria-hidden="true" className="kbd">
              Ctrl ↵
            </span>
          </motion.button>
        </div>
      </div>
      <div className="examples">
        <span className="examples-label">Try:</span>
        {EXAMPLES.map((example) => (
          <button
            key={example.label}
            type="button"
            className="chip"
            disabled={busy}
            onClick={() => setMessage(example.text)}
          >
            {example.label}
          </button>
        ))}
        <button
          type="button"
          className="chip ghost"
          disabled={busy}
          onClick={onSample}
          title={sampleMessage}
        >
          ▶ Watch a recorded answer
        </button>
      </div>
    </form>
  )
}
