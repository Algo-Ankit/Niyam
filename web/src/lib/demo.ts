import recorded from '../fixtures/opt-filing-window.json'
import { STAGES, type Reply, type Stage } from './types'

// A real reply from the live pipeline, replayed so the page can be explored without spending
// free-tier quota. Stage times are the ones measured on that run; the replay runs them 4x faster.
export const DEMO_MESSAGE =
  'I graduated 2026-05-15 and my DSO recommended OPT on 2026-05-20. What is my filing window?'
export const DEMO_AS_OF = '2026-06-01'
const RECORDED_MS: Record<Stage, number> = {
  extract: 9162,
  rules: 0,
  retrieve: 737,
  rerank: 951,
  explain: 10861,
  verify: 1,
}
const SPEED_UP = 4

export async function replay(
  onStage: (stage: Stage, ms: number) => void,
  signal: AbortSignal,
): Promise<Reply> {
  for (const stage of STAGES) {
    await wait(Math.max(180, RECORDED_MS[stage] / SPEED_UP), signal)
    onStage(stage, RECORDED_MS[stage])
  }
  return recorded as Reply
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('aborted', 'AbortError'))
    })
  })
}
