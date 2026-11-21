import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'

import { STAGE_INFO, formatMs } from '../lib/format'
import { STAGES, type StageTimes } from '../lib/types'

const SLOW_AFTER_MS = 15_000 // D74
const DEADLINE_S = 50 // the server's ask deadline, ASK_DEADLINE_SECONDS (D71)

interface Props {
  times: StageTimes
  running: boolean
  startedAt: number | null
  failed: boolean
}

/** The six real pipeline stages, lighting up as the server reports each one finished. */
export function Pipeline({ times, running, startedAt, failed }: Props) {
  const elapsed = useElapsed(running ? startedAt : null)
  const doneCount = STAGES.filter((s) => times[s] !== undefined).length
  const current = running ? STAGES[doneCount] : undefined
  const slow = running && elapsed >= SLOW_AFTER_MS

  return (
    <section className="pipeline card" aria-labelledby="pipeline-title">
      <div className="pipeline-head">
        <h2 id="pipeline-title">How this answer is being made</h2>
        <span className={`elapsed${running ? ' live' : ''}`} aria-live="off">
          {running ? `${(elapsed / 1000).toFixed(1)} s` : failed ? 'Stopped' : 'Done'}
        </span>
      </div>
      {slow && (
        <p className="slow-note" role="status">
          The model is slow right now. Still working; it stops at {DEADLINE_S} s.
        </p>
      )}
      <div className="track" aria-hidden="true">
        <motion.div
          className={`track-fill${failed ? ' failed' : ''}`}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: doneCount / STAGES.length }}
          transition={{ type: 'spring', stiffness: 90, damping: 20 }}
        />
      </div>
      <ol className="stages">
        {STAGES.map((stage, i) => {
          const info = STAGE_INFO[stage]
          const ms = times[stage]
          const state = ms !== undefined ? 'done' : stage === current ? 'active' : 'idle'
          return (
            <motion.li
              key={stage}
              className={`stage ${state} who-${info.who.toLowerCase()}`}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <div className="node">
                {state === 'active' && <span className="pulse" />}
                <AnimatePresence mode="wait" initial={false}>
                  {state === 'done' ? (
                    <motion.svg
                      key="check"
                      viewBox="0 0 24 24"
                      className="check"
                      initial={{ scale: 0.4, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                    >
                      <motion.path
                        d="M5 12.5l4.5 4.5L19 7.5"
                        initial={{ pathLength: 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ duration: 0.35 }}
                      />
                    </motion.svg>
                  ) : (
                    <motion.span key="n" exit={{ opacity: 0 }}>
                      {i + 1}
                    </motion.span>
                  )}
                </AnimatePresence>
              </div>
              <div className="stage-text">
                <div className="stage-label">
                  {info.label} <span className="who">{info.who}</span>
                </div>
                <div className="stage-note">{info.note}</div>
                <div className="stage-ms">{ms !== undefined ? formatMs(ms) : ' '}</div>
              </div>
            </motion.li>
          )
        })}
      </ol>
      <p className="sr-only" aria-live="polite">
        {current ? `${STAGE_INFO[current].label} in progress` : ''}
      </p>
    </section>
  )
}

function useElapsed(startedAt: number | null): number {
  const [now, setNow] = useState(() => performance.now())
  useEffect(() => {
    if (startedAt === null) return
    const timer = setInterval(() => setNow(performance.now()), 100)
    return () => clearInterval(timer)
  }, [startedAt])
  return startedAt === null ? 0 : Math.max(0, now - startedAt)
}
