import { motion } from 'motion/react'

import { STATUS_INFO, formatDate, ruleTitle, toDate } from '../lib/format'
import type { Finding } from '../lib/types'

const DAY = 86_400_000

/** Each dated finding on one shared date axis, with a marker for the answer's "today". */
export function Timeline({ findings, asOf }: { findings: Finding[]; asOf: string }) {
  const dates = [asOf, ...findings.flatMap((f) => [f.opens, f.closes])].filter(
    (d): d is string => d !== null,
  )
  const times = dates.map((d) => toDate(d).getTime())
  const pad = Math.max(7 * DAY, (Math.max(...times) - Math.min(...times)) * 0.06)
  const start = Math.min(...times) - pad
  const span = Math.max(...times) + pad - start
  const at = (iso: string) => ((toDate(iso).getTime() - start) / span) * 100
  const today = at(asOf)

  return (
    <div className="timeline">
      <div className="tl-axis" aria-hidden="true">
        <span style={{ left: '0%' }}>{formatDate(new Date(start).toISOString().slice(0, 10))}</span>
        <span style={{ left: '100%' }}>
          {formatDate(new Date(start + span).toISOString().slice(0, 10))}
        </span>
      </div>
      <div className="tl-body">
      <motion.div
        className="tl-today"
        style={{ left: `${today}%` }}
        initial={{ scaleY: 0 }}
        animate={{ scaleY: 1 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        aria-hidden="true"
      >
        <span>Today</span>
      </motion.div>
      <ul className="tl-rows">
        {findings.map((finding, i) => {
          const tone = STATUS_INFO[finding.status].tone
          const from = finding.opens ? at(finding.opens) : null
          const to = finding.closes ? at(finding.closes) : null
          const label = describe(finding)
          return (
            <li key={`${finding.rule}-${i}`} className="tl-row">
              <div className="tl-row-head">
                <span className="tl-label">{ruleTitle(finding.rule)}</span>
                <span className="tl-date">{label}</span>
              </div>
              <div className="tl-lane" role="img" aria-label={label} title={label}>
                {from !== null && to !== null ? (
                  <motion.div
                    className={`tl-bar tone-${tone}`}
                    style={{ left: `${from}%`, width: `${Math.max(to - from, 0.8)}%` }}
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: 0.8, delay: 0.25 + i * 0.1, ease: [0.22, 1, 0.36, 1] }}
                  />
                ) : (
                  <motion.div
                    className={`tl-dot tone-${tone}`}
                    style={{ left: `${(to ?? from) ?? 0}%` }}
                    initial={{ scale: 0, rotate: 45 }}
                    animate={{ scale: 1, rotate: 45 }}
                    transition={{ type: 'spring', stiffness: 260, damping: 16, delay: 0.3 + i * 0.1 }}
                  />
                )}
              </div>
            </li>
          )
        })}
      </ul>
      </div>
    </div>
  )
}

function describe(finding: Finding): string {
  if (finding.opens && finding.closes)
    return `${formatDate(finding.opens)} → ${formatDate(finding.closes)}`
  if (finding.closes) return `by ${formatDate(finding.closes)}`
  return `from ${formatDate(finding.opens ?? '')}`
}
