import { useEffect, useState } from 'react'

/** Seconds until `until` (a Date.now() timestamp), ticking every second; 0 once it has passed. */
export function useSecondsLeft(until: number | null): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (until === null) return
    setNow(Date.now())
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [until])
  return until === null ? 0 : Math.max(0, (until - now) / 1000)
}
