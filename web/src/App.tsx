import { MotionConfig } from 'motion/react'
import { useEffect, useRef, useState } from 'react'

import { AskForm } from './components/AskForm'
import { Backdrop } from './components/Backdrop'
import { ErrorNotice } from './components/ErrorNotice'
import { Footer } from './components/Footer'
import { Hero } from './components/Hero'
import { HowItWorks } from './components/HowItWorks'
import { Pipeline } from './components/Pipeline'
import { Results } from './components/Results'
import { ask, fetchHealth } from './lib/api'
import { DEMO_AS_OF, DEMO_MESSAGE, replay } from './lib/demo'
import { localToday } from './lib/format'
import {
  AskError,
  MAX_HISTORY_TURNS,
  type ConversationTurn,
  type HistoryTurn,
  type Reply,
  type Stage,
  type StageTimes,
} from './lib/types'
import { useSecondsLeft } from './lib/useSecondsLeft'

type Phase =
  | { kind: 'idle' }
  | { kind: 'running'; startedAt: number; sample: boolean }
  | { kind: 'error'; error: AskError }

interface SampleRun {
  reply: Reply
  asOf: string
  times: StageTimes
}

export function App() {
  const [turns, setTurns] = useState<ConversationTurn[]>([])
  const [sampleRun, setSampleRun] = useState<SampleRun | null>(null)
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [times, setTimes] = useState<StageTimes>({})
  const [snapshot, setSnapshot] = useState<string | null>(null)
  const [blockedUntil, setBlockedUntil] = useState<number | null>(null)
  const secondsLeft = useSecondsLeft(blockedUntil)
  const lastMessage = useRef<string | null>(null)
  const nextTurnId = useRef(1)
  const controller = useRef<AbortController | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const activeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const abort = new AbortController()
    fetchHealth(abort.signal)
      .then((health) => setSnapshot(health.corpus_snapshot))
      .catch(() => setSnapshot(null))
    return () => abort.abort()
  }, [])

  function resetConversation() {
    controller.current?.abort()
    controller.current = null
    lastMessage.current = null
    setTurns([])
    setSampleRun(null)
    setTimes({})
    setPhase({ kind: 'idle' })
  }

  async function run(message: string, sample: boolean) {
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    const asOf = sample ? DEMO_AS_OF : localToday()
    if (!sample) {
      lastMessage.current = message
      setSampleRun(null)
    }
    const collectedTimes: StageTimes = {}
    const onStage = (stage: Stage, ms: number) => {
      collectedTimes[stage] = ms
      setTimes((t) => ({ ...t, [stage]: ms }))
    }
    setTimes({})
    setPhase({ kind: 'running', startedAt: performance.now(), sample })
    const scrollTarget = turns.length > 0 && !sample ? activeRef.current : resultsRef.current
    requestAnimationFrame(() =>
      scrollTarget?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
    )
    try {
      if (sample) {
        const reply = await replay(onStage, abort.signal)
        setSampleRun({ reply, asOf, times: collectedTimes })
        setPhase({ kind: 'idle' })
        return
      }
      const context =
        turns.length > 0
          ? {
              history: turns.slice(-MAX_HISTORY_TURNS).map(
                (t): HistoryTurn => ({
                  question: (t.reply.question || t.message).slice(0, 500),
                  answer: t.reply.explanation ? t.reply.explanation.slice(0, 1500) : null,
                }),
              ),
              priorFacts: turns[turns.length - 1]?.reply.facts ?? null,
            }
          : undefined
      const reply = await ask(message, asOf, onStage, abort.signal, context)
      const turn: ConversationTurn = {
        id: nextTurnId.current++,
        message,
        reply,
        asOf,
        times: collectedTimes,
      }
      setTurns((prev) => [...prev, turn])
      setPhase({ kind: 'idle' })
    } catch (error) {
      if (abort.signal.aborted) return
      const askError =
        error instanceof AskError ? error : new AskError('internal', 'Something went wrong.')
      if (askError.kind === 'limited' && askError.retryAfterSeconds !== null) {
        setBlockedUntil(Date.now() + askError.retryAfterSeconds * 1000)
      }
      setPhase({ kind: 'error', error: askError })
    }
  }

  const running = phase.kind === 'running'
  const blockedSeconds = blockedUntil !== null && secondsLeft > 0 ? secondsLeft : 0
  const stageStarted = Object.keys(times).length > 0
  const hasConversation = turns.length > 0
  const earlierTurns = hasConversation ? turns.slice(0, -1) : []
  const latestTurn = hasConversation ? (turns[turns.length - 1] ?? null) : null
  // Hidden for a refusal before any stage (D74) and for a greeting or unrelated reply (D72):
  // in both cases the six-stage tracker would show an empty, misleading "Stopped".
  const showActivePipeline = running || (phase.kind === 'error' && stageStarted)
  const showLatestPipeline =
    !showActivePipeline && latestTurn !== null && latestTurn.reply.kind === 'question'
  const showSamplePipeline = !hasConversation && !showActivePipeline && sampleRun !== null
  const retryable =
    phase.kind === 'error' &&
    ['busy', 'internal', 'network'].includes(phase.error.kind) &&
    lastMessage.current !== null

  return (
    <MotionConfig reducedMotion="user">
      <Backdrop />
      <main>
        <Hero>
          {hasConversation ? (
            <div className="card session-bar">
              <span className="muted small">
                Active conversation · {turns.length} {turns.length === 1 ? 'question' : 'questions'}{' '}
                · Stored in this tab only — lost when you reload or leave
              </span>
              <button type="button" className="chip" disabled={running} onClick={resetConversation}>
                New conversation
              </button>
            </div>
          ) : (
            <AskForm
              busy={running}
              blockedSeconds={blockedSeconds}
              sampleMessage={DEMO_MESSAGE}
              onAsk={(message) => void run(message, false)}
              onSample={() => void run(DEMO_MESSAGE, true)}
            />
          )}
        </Hero>

        <div ref={resultsRef} className="results-anchor">
          {earlierTurns.map((turn, idx) => (
            <details key={turn.id} className="card prior-turn">
              <summary className="prior-turn-summary">
                <div className="prior-turn-head">
                  <span className="asked">Question {idx + 1}</span>
                  <span className="prior-turn-q">{turn.reply.question || turn.message}</span>
                </div>
                {turn.reply.explanation && (
                  <p className="prior-turn-preview muted small">{turn.reply.explanation}</p>
                )}
              </summary>
              <div className="prior-turn-body">
                <Results
                  reply={turn.reply}
                  asOf={turn.asOf}
                  sample={false}
                  turnPrefix={`t${turn.id}-`}
                />
              </div>
            </details>
          ))}

          {latestTurn && (
            <>
              {showLatestPipeline && (
                <Pipeline
                  times={latestTurn.times}
                  running={false}
                  startedAt={null}
                  failed={false}
                />
              )}
              <Results
                key={latestTurn.id}
                reply={latestTurn.reply}
                asOf={latestTurn.asOf}
                sample={false}
                turnPrefix={`t${latestTurn.id}-`}
              />
            </>
          )}

          <div ref={activeRef} className="results-anchor">
            {showSamplePipeline && sampleRun && (
              <>
                <Pipeline
                  times={sampleRun.times}
                  running={false}
                  startedAt={null}
                  failed={false}
                />
                <Results
                  reply={sampleRun.reply}
                  asOf={sampleRun.asOf}
                  sample={true}
                  turnPrefix="sample-"
                />
              </>
            )}

            {showActivePipeline && (
              <Pipeline
                times={times}
                running={running}
                startedAt={phase.kind === 'running' ? phase.startedAt : null}
                failed={phase.kind === 'error'}
              />
            )}

            {phase.kind === 'error' && (
              <ErrorNotice
                error={phase.error}
                secondsLeft={blockedSeconds}
                onRetry={
                  retryable && blockedSeconds === 0
                    ? () => void run(lastMessage.current ?? '', false)
                    : null
                }
              />
            )}

            {hasConversation && (
              <AskForm
                busy={running}
                blockedSeconds={blockedSeconds}
                sampleMessage={DEMO_MESSAGE}
                onAsk={(message) => void run(message, false)}
                onSample={() => void run(DEMO_MESSAGE, true)}
                followUp
                turnCount={turns.length}
                onReset={resetConversation}
              />
            )}
          </div>
        </div>

        <HowItWorks />
      </main>
      <Footer snapshot={snapshot} />
    </MotionConfig>
  )
}
