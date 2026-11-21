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
import { AskError, type Reply, type Stage, type StageTimes } from './lib/types'

type Phase =
  | { kind: 'idle' }
  | { kind: 'running'; startedAt: number }
  | { kind: 'done'; reply: Reply; asOf: string; sample: boolean }
  | { kind: 'error'; error: AskError }

export function App() {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [times, setTimes] = useState<StageTimes>({})
  const [snapshot, setSnapshot] = useState<string | null>(null)
  const controller = useRef<AbortController | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const abort = new AbortController()
    fetchHealth(abort.signal)
      .then((health) => setSnapshot(health.corpus_snapshot))
      .catch(() => setSnapshot(null))
    return () => abort.abort()
  }, [])

  async function run(message: string, sample: boolean) {
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    const asOf = sample ? DEMO_AS_OF : localToday()
    const onStage = (stage: Stage, ms: number) => setTimes((t) => ({ ...t, [stage]: ms }))
    setTimes({})
    setPhase({ kind: 'running', startedAt: performance.now() })
    resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    try {
      const reply = sample
        ? await replay(onStage, abort.signal)
        : await ask(message, asOf, onStage, abort.signal)
      setPhase({ kind: 'done', reply, asOf, sample })
    } catch (error) {
      if (abort.signal.aborted) return
      setPhase({
        kind: 'error',
        error: error instanceof AskError ? error : new AskError('internal', 'Something went wrong.'),
      })
    }
  }

  const running = phase.kind === 'running'
  // A greeting or unrelated reply skips the pipeline (D72), so its tracker would be misleading.
  const showPipeline =
    phase.kind !== 'idle' && !(phase.kind === 'done' && phase.reply.kind !== 'question')

  return (
    <MotionConfig reducedMotion="user">
      <Backdrop />
      <main>
        <Hero>
          <AskForm
            busy={running}
            sampleMessage={DEMO_MESSAGE}
            onAsk={(message) => void run(message, false)}
            onSample={() => void run(DEMO_MESSAGE, true)}
          />
        </Hero>

        <div ref={resultsRef} className="results-anchor">
          {showPipeline && (
            <Pipeline
              times={times}
              running={running}
              startedAt={phase.kind === 'running' ? phase.startedAt : null}
              failed={phase.kind === 'error'}
            />
          )}
          {phase.kind === 'error' && <ErrorNotice error={phase.error} />}
          {phase.kind === 'done' && (
            <Results reply={phase.reply} asOf={phase.asOf} sample={phase.sample} />
          )}
        </div>

        <HowItWorks />
      </main>
      <Footer snapshot={snapshot} />
    </MotionConfig>
  )
}
